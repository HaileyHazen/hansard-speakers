import pandas as pd
from typing import Dict, List, Optional
import logging
import time
import sys
from multiprocessing import Process, Queue, cpu_count
import argparse
from hansard import *
from hansard.speaker import *


CPU_CORES = 1

SPEAKERS: List[SpeakerReplacement] = []
SPEAKER_DICT: Dict[str, SpeakerReplacement] = {}

CORRECTIONS: Dict[str, str] = {}

OFFICE_DICT: Dict[str, Office] = {}
FULL_ALIAS_DICT: Dict[str, List[SpeakerReplacement]] = {}
HOLDINGS: List[OfficeHolding] = []

EXCHEQUER_DF: Optional[pd.DataFrame] = None
PM_DF: Optional[pd.DataFrame] = None

OFFICE_TERMS_DF: Optional[pd.DataFrame] = None


def parse_config():
    global CPU_CORES
    parser = argparse.ArgumentParser()
    parser.add_argument('--cores', nargs=1, default=1, type=int, help='Number of cores to use.')
    args = parser.parse_args()
    CPU_CORES = args.cores[0]
    if CPU_CORES < 0 or CPU_CORES > cpu_count():
        raise ValueError('Invalid core number specified.')


def init_logging():
    if not os.path.isdir('logs'):
        os.mkdir('logs')

    logging.basicConfig(filename='logs/{:%y%m%d_%H%M%S}.log'.format(datetime.now()),
                        format='%(asctime)s|%(levelname)s|%(message)s',
                        datefmt='%H:%M:%S',
                        level=logging.DEBUG)

    # Uncomment to log to stdout as well.
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    logging.debug('Initializing...\n')

    logging.debug(f'Utilizing {CPU_CORES} cores...')


def load_corrections():
    global CORRECTIONS
    logging.debug('Loading misspellings...')

    misspellings: pd.DataFrame = pd.read_csv('data/misspellings_dictionary.csv', sep=',', encoding='ISO-8859-1')
    misspellings['correct'] = misspellings['correct'].fillna('')
    CORRECTIONS = {k.lower(): v for k, v in zip(misspellings['incorrect'], misspellings['correct'])}

    ocr_title_errs: pd.DataFrame = pd.read_csv('data/common_OCR_errors_titles.csv', sep=',')
    ocr_title_errs['CORRECT'] = ocr_title_errs['CORRECT'].fillna('')
    ocr_err_dict = {k.lower(): v for k, v in zip(ocr_title_errs['INCORRECT'], ocr_title_errs['CORRECT'])}
    CORRECTIONS.update(ocr_err_dict)


def parse_mps():
    global SPEAKERS, SPEAKER_DICT, FULL_ALIAS_DICT

    logging.debug('Reading mps.csv...')
    mps: pd.DataFrame = pd.read_csv('data/mps.csv', sep=',')
    mps['mp.dob'] = pd.to_datetime(mps['mp.dob'], format=DATE_FORMAT)
    mps['mp.dod'] = pd.to_datetime(mps['mp.dod'], format=DATE_FORMAT)

    malformed_mp_date = 0
    malformed_mp_name = 0
    missing_fn_name = 0
    missing_sn_name = 0

    logging.debug('Parsing mps.csv...')
    for index, row in mps.iterrows():
        dob = row['mp.dob']

        if pd.isna(dob):
            # TODO: fix members without DOB
            continue

        dod = row['mp.dod']
        if pd.isna(dod):
            # Assume that the speaker is still alive.
            dod = datetime.now()

        fullname, firstname, surname = row['mp.name'], row['mp.fname'], row['mp.sname']

        if type(firstname) != str:
            missing_fn_name += 1
            logging.debug(f'Missing first name at row: {index}. Fullname is {row["mp.name"]}. Surname is {row["mp.sname"]}.')
            continue
        elif type(surname) != str:
            missing_sn_name += 1
            logging.debug(f'Missing surname at row: {index}. Fullname is {row["mp.name"]}. First name is {row["mp.fname"]}.')
            continue

        defined_aliases = []
        for alias in MP_ALIAS_PATTERN.finditer(fullname):
            defined_aliases.append(alias.group(1))

        MP_ALIAS_PATTERN.sub('', fullname)

        # if '(' in row['mp.name']:
        #     malformed_mp_name += 1
        #     logging.debug(f'Unhandled character at row: {index}. Fullname is {row["mp.name"]}.')
        #     continue

        try:
            speaker = SpeakerReplacement(fullname, firstname, surname, row['member.id'], dob, dod)
            SPEAKERS.append(speaker)
            SPEAKER_DICT[speaker.member_id] = speaker

            for alias in speaker.aliases:
                FULL_ALIAS_DICT.setdefault(alias, []).append(speaker)

            for alias in defined_aliases:
                FULL_ALIAS_DICT.setdefault(alias, []).append(speaker)

        except FirstNameMissingError:
            continue
        except LastNameMissingError:
            continue

    logging.info(f'{malformed_mp_date} speakers with malformed dates', )
    logging.info(f'{malformed_mp_name} speakers with malformed fullnames', )
    logging.info(f'{missing_fn_name} speakers with malformed first names', )
    logging.info(f'{missing_sn_name} speakers with malformed surnames', )
    logging.info(f'{len(SPEAKERS)} speakers sucessfully loaded out of {len(mps)} rows.')


def parse_offices():
    global SPEAKER_DICT, OFFICE_DICT, HOLDINGS, EXCHEQUER_DF, PM_DF, OFFICE_TERMS_DF

    logging.info('Loading offices...')
    offices_df = pd.read_csv('data/offices.csv', sep=',')
    for index, row in offices_df.iterrows():
        office = Office(row['office_id'], row['name'])
        OFFICE_DICT[office.id] = office

    logging.info('Loading office holdings...')
    holdings_df = pd.read_csv('data/officeholdings.csv', sep=',')
    unknown_members = 0
    unknown_offices = 0
    invalid_office_dates = 0
    for index, row in holdings_df.iterrows():
        # oh_id,member_id,office_id,start_date,end_date
        try:
            holding_start = datetime.strptime(row['start_date'], DATE_FORMAT)

            if type(row['end_date']) == float:
                holding_end = datetime.now()
            else:
                holding_end = datetime.strptime(row['end_date'], DATE_FORMAT)

        except TypeError:
            logging.debug(f'Invalid office holding date in row {index}. start_date is {row["start_date"]}')
            invalid_office_dates += 1
            continue

        if row['member_id'] not in SPEAKER_DICT:
            logging.debug(f'Member with id {row["member_id"]} not found for office holding at row {index}')
            unknown_members += 1
            continue

        if row['office_id'] not in OFFICE_DICT:
            logging.debug(f'Office holding at row {index} linked to invalid office id: {row["office_id"]}')
            unknown_offices += 1
            continue

        holding = OfficeHolding(row['oh_id'], row['member_id'], row['office_id'], holding_start, holding_end,
                                OFFICE_DICT[row['office_id']])
        HOLDINGS.append(holding)

    logging.debug(f'{unknown_members} office holding rows had unknown members.')
    logging.debug(f'{unknown_offices} office holding rows had unknown offices.')
    logging.debug(f'{len(HOLDINGS)} office holdings successfully loaded out of {len(holdings_df)} rows.')

    EXCHEQUER_DF = pd.read_csv('data/chancellor_of_the_exchequer.csv', sep=',')
    EXCHEQUER_DF['started_service'] = pd.to_datetime(EXCHEQUER_DF['started_service'], format=DATE_FORMAT2)
    EXCHEQUER_DF['ended_service'] = pd.to_datetime(EXCHEQUER_DF['ended_service'], format=DATE_FORMAT2)

    PM_DF = pd.read_csv('data/prime_ministers.csv', sep=',')
    PM_DF['started_service'] = pd.to_datetime(PM_DF['started_service'], format=DATE_FORMAT2)
    PM_DF['ended_service'] = pd.to_datetime(PM_DF['ended_service'], format=DATE_FORMAT2)

    OFFICE_TERMS_DF = pd.read_csv('data/liparm_members.csv', sep=',')
    OFFICE_TERMS_DF['start_term'] = pd.to_datetime(OFFICE_TERMS_DF['start_term'], format=DATE_FORMAT)
    OFFICE_TERMS_DF['end_term'] = pd.to_datetime(OFFICE_TERMS_DF['end_term'], format=DATE_FORMAT)


if __name__ == '__main__':
    parse_config()
    init_logging()
    load_corrections()
    parse_mps()
    parse_offices()

    from hansard.worker import worker_function

    inq = Queue()
    outq = Queue()

    logging.info('Loading processes...')

    hit = 0
    ambiguities = 0
    numrows = 0
    index = 0

    process_args = (inq, outq, HOLDINGS, FULL_ALIAS_DICT, CORRECTIONS, EXCHEQUER_DF, PM_DF, OFFICE_TERMS_DF)
    processes = [Process(target=worker_function, args=process_args) for _ in range(CPU_CORES)]

    for p in processes:
        p.start()

    missed_df = pd.DataFrame()
    ambiguities_df = pd.DataFrame()

    missed_indexes = []
    ambiguities_indexes = []

    logging.info('Loading text...')

    for chunk in pd.read_csv(DATA_FILE,
                             sep=',',
                             chunksize=CHUNK_SIZE,
                             usecols=['speechdate', 'speaker']):  # type: pd.DataFrame

        chunk['speechdate'] = pd.to_datetime(chunk['speechdate'], format=DATE_FORMAT)

        t0 = time.time()

        for index, speechdate, speaker in chunk.itertuples():
            inq.put((index, speechdate, speaker))

        for i in range(len(chunk)):
            if i % 100000 == 0:
                logging.debug(f'Chunk Progress: {i}/{len(chunk)}')
            is_hit, is_ambig, missed_i = outq.get()
            if is_hit:
                hit += 1
            elif is_ambig:
                ambiguities += 1
                ambiguities_indexes.append(missed_i)
            else:
                missed_indexes.append(missed_i)

        missed_df = missed_df.append(chunk.loc[missed_indexes, :])
        del missed_indexes[:]

        ambiguities_df = ambiguities_df.append(chunk.loc[ambiguities_indexes, :])
        del ambiguities_indexes[:]

        numrows += len(chunk.index)
        logging.info(f'{len(chunk.index)} processed in {int((time.time() - t0) * 100) / 100} seconds')
        logging.info(f'Processed {numrows} rows so far.')

        # Uncomment break to process only 1 chunk.
        # break

    logging.info('Writing missed speakers data...')
    missed_df.to_csv(os.path.join(OUTPUT_DIR, 'missed_speakers.csv'))
    logging.info('Writing ambiguous speakers data...')
    ambiguities_df.to_csv(os.path.join(OUTPUT_DIR, 'ambig_speakers.csv'))
    logging.info('Complete.')

    for process in processes:
        process.terminate()

    logging.info(f'{hit} hits')
    logging.info(f'{ambiguities} ambiguities')
    logging.info(f'{index} rows parsed')
    logging.info('Exiting...')
