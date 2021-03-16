import multiprocessing
from queue import Empty
from hansard.loader import DataStruct
from datetime import datetime
import pandas as pd
import re


compile_regex = lambda x: (re.compile(x[0]), x[1])


REGEX_PRE_CORRECTIONS = [
    (r'(?:\([^()]+\))', ''),  # Remove all text within parenthesis, including parenthesis
]
REGEX_PRE_CORRECTIONS = list(map(compile_regex, REGEX_PRE_CORRECTIONS))

REGEX_POST_CORRECTIONS = [

    # Regex for misspelled leading the
    (r'^this +', 'the '),
    ('^thr +', 'the '),
    ('^then +', 'the '),
    ('^tee +', 'the '),
    ('^thh +', 'the '),
    ('^tue +', 'the '),
    ('^tmk +', 'the '),
    ('^tub +', 'the '),

    (r'^the +', ''),  # Remove leading "the"

    (r'^me +', 'mr '),  # Leading me -> mr

    ('^lerd +', 'lord '),
    ('^lobd +', 'lord '),

    ('^earb +', 'earl '),

    ('^dike +', 'duke '),
    
    # Fix leading Sir
    ('^sib +', 'sir '),
    ('^sin +', 'sir '),
    ('^sin +', 'sir '),
    ('^sit +', 'sir '),
    ('^sip +', 'sir '),
    ('^siu +', 'sir '),
    ('^sik +', 'sir '),
    (r'^sat +', 'sir '), 
]

REGEX_POST_CORRECTIONS = list(map(compile_regex, REGEX_POST_CORRECTIONS))


def match_term(df: pd.DataFrame, date: datetime) -> pd.DataFrame:
    return df[(date >= df['started_service']) & (date < df['ended_service'])]


# This function will run per core.
def worker_function(inq: multiprocessing.Queue,
                    outq: multiprocessing.Queue,
                    data: DataStruct):
    from . import cleanse_string

    # Lookup optimization
    misspellings_dict = data.corrections
    holdings = data.holdings
    alias_dict = data.alias_dict
    terms_df = data.term_df
    speaker_dict = data.speaker_dict
    honorary_title_df = data.honorary_titles_df
    office_title_dfs = data.office_position_dfs
    lord_titles_df = data.lord_titles_df

    hitcount = 0
    missed_indexes = []
    ambiguities_indexes = []

    MATCH_CACHE = {}

    def postprocess(string_val: str) -> str:
        for k, v in REGEX_POST_CORRECTIONS:
            string_val = re.sub(k, v, string_val)
        return string_val.strip()

    def preprocess(string_val: str) -> str:
        for k, v in REGEX_PRE_CORRECTIONS:
            string_val = re.sub(k, v, string_val)

        string_val = cleanse_string(string_val)
        for misspell in misspellings_dict:
            string_val = string_val.replace(misspell, misspellings_dict[misspell])
        string_val = cleanse_string(string_val)
        return postprocess(string_val)

    while True:
        try:
            chunk: pd.DataFrame = inq.get(block=True)
        except Empty:
            continue
        else:
            if chunk is None:
                # This is our signal that we are done here. Every other worker thread will get a similar signal.
                return

            chunk['speaker_modified'] = chunk['speaker'].map(preprocess)

            for i, speechdate, unmodified_target, target in chunk.itertuples():
                match = MATCH_CACHE.get((target, speechdate), None)
                ambiguity: bool = False
                possibles = []
                query = []

                if not match:
                    # Try office position
                    for position in office_title_dfs:
                        if position in target:
                            query = match_term(office_title_dfs[position], speechdate)
                            break

                if not match and not len(query):
                    # Try honorary title
                    condition = (speechdate >= honorary_title_df['started_service']) &\
                                (speechdate < honorary_title_df['ended_service']) &\
                                (honorary_title_df['honorary_title'].str.contains(target, regex=False))
                    query = honorary_title_df[condition]

                if not match and not len(query):
                    # try aliases.
                    condition = (speechdate >= lord_titles_df['start']) &\
                                (speechdate < lord_titles_df['end']) &\
                                (lord_titles_df['alias'].str.contains(target, regex=False))
                    query = lord_titles_df[condition]

                if not match:
                    if len(query) == 1:
                        speaker_id = query.iloc[0]['corresponding_id']
                        if speaker_id != 'N/A':
                            # TODO: setup logging to keep track of when == n/a
                            # TODO: fix IDs missing due to being malformed entries in mps.csv
                            # match = speaker_dict[int(speaker_id)]
                            # for now use speaker_id to ensure this counts as a match
                            match = speaker_id
                    elif len(query) > 1:
                        ambiguity = True

                # can we get ambiguities with office names?
                if not match:
                    for holding in holdings:
                        if holding.matches(target, speechdate, cleanse=False):
                            match = holding
                            break

                if not match:
                    possibles = alias_dict.get(target)
                    if possibles is not None:
                        possibles = [speaker for speaker in possibles if speaker.matches(target, speechdate, cleanse=False)]
                        if len(possibles) == 1:
                            match = possibles[0]
                        else:
                            ambiguity = True

                if ambiguity and possibles:
                    speaker_ids = {speaker.id for speaker in possibles}

                    query = terms_df[(terms_df['member.id'].isin(speaker_ids)) &
                                     (terms_df['start_term'] <= speechdate) &
                                     (speechdate <= terms_df['end_term'])]
                    if len(query) == 1:
                        ambiguity = False
                        match = query.iloc[0]['fullname'].lower()

                if match is not None:
                    hitcount += 1
                    MATCH_CACHE[(target, speechdate)] = match
                elif ambiguity:
                    ambiguities_indexes.append(i)
                else:
                    missed_indexes.append(i)

            outq.put((hitcount, chunk.loc[missed_indexes, :], chunk.loc[ambiguities_indexes, :]))
            hitcount = 0
            del missed_indexes[:]
            del ambiguities_indexes[:]
