import multiprocessing
from queue import Empty
from typing import Tuple, Optional, List, Dict

import numpy

from hansard.disambiguate import disambiguate
from hansard.loader import DataStruct
from datetime import datetime
import pandas as pd
import re

from hansard.speaker import SpeakerReplacement
from util.edit_distance import within_distance_four, within_distance_two, is_distance_one


OUTPUT_COLUMN = 'disambig_speaker'

compile_regex = lambda x: (re.compile(x[0]), x[1])


REGEX_PRE_CORRECTIONS = [
    (r'(?:\([^()]+\))', ''),  # Remove all text within parenthesis, including parenthesis    
]

PARENTHESIS_REGEX = re.compile(r'(?:\(([^()]+)\))')


REGEX_PRE_CORRECTIONS = list(map(compile_regex, REGEX_PRE_CORRECTIONS))

REGEX_POST_CORRECTIONS = [

    # Regex for misspelled leading the
    ('^this +', 'the '),
    ('^thr +', 'the '),
    ('^then +', 'the '),
    ('^tee +', 'the '),
    ('^thh +', 'the '),
    ('^tue +', 'the '),
    ('^tmk +', 'the '),
    ('^tub +', 'the '),
    ('^he +', 'the '),
    ('^tim +', 'the '),
    ('^tme +', 'the '),
    ('^tihe +', 'the '),
    ('^thk +', 'the '),
    ('^thb +', 'the '),
    ('^tre +', 'the '),
    ('^tile +', 'the '),
    ('^tiie +', 'the '),
    ('^t he +', 'the '),

    ('^the +', ''),  # Remove leading "the"

    ('^me +', 'mr '),  # Leading me -> mr
    ('^mb +', 'mr '),
    ('^mer +', 'mr '),
    ('^mh +', 'mr '),
    ('^mil +', 'mr '),
    ('^mk +', 'mr '),
    ('^mp +', 'mr '),
    ('^ma +', 'mr '),
    ('^mi +', 'mr '),
    
    ('^m r +', 'mr '),  # Fix leading spaced out mr
    
    ('^dir +', 'dr '),
    ('^dk +', 'dr '),
    ('^de +','dr '),
    
    (' image srcsvpi colcol', ''),
    
    ('^marquis +', 'marquess '),
    ('^mauquess +', 'marquess '),
    ('^manquess +', 'marquess '),
    ('^marguess +', 'marquess '),
    ('^marquees +', 'marquess '),
    ('^marques +', 'marquess '),
    ('^marquese +', 'marquess '),
    ('^marquese +', 'marquess '),
    ('^marquesss +', 'marquess '),
    ('^mabquess +', 'marquess '),
    ('^maeqttess +', 'marquess '),
    ('^maequess +', 'marquess '),
    ('^marqdess +', 'marquess '),
    ('^marqiess +', 'marquess '),
    ('^marqtjess +', 'marquess '),
    
    ('^vicount +', 'viscount '),
    ('^vicsount +', 'viscount '),
    ('^vis- count +', 'viscount '),
    ('^viscocnt +', 'viscount '),
    ('^viscodnt +', 'viscount '),
    ('^viscolunt +', 'viscount '),
    ('^viscotint +', 'viscount '),
    ('^viscotjnt +', 'viscount '),
    ('^viscouint +', 'viscount '),
    ('^viscoun +', 'viscount '),
    ('^viscouxt +', 'viscount '),
    ('^viscwnt +', 'viscount '),
    ('^visoount +', 'viscount '),
    ('^vtscount +', 'viscount '),
    ('^viscuont +', 'viscount '),
    ('^viscoust +', 'viscount '),
    ('^viscounty +', 'viscount '),
    ('^visct +', 'viscount '),
    ('^lord viscount +', 'viscount '),
    
    ('^lord speaker +', 'speaker '),

    ('^lerd +', 'lord '),
    ('^lobd +', 'lord '),
    ('^loan +', 'lord '),
    ('^load +', 'lord '),
    ('^lokd +', 'lord '),
    ('^lold +', 'lord '),
    ('^lore +', 'lord '),
    ('^lorn +', 'lord '),
    ('^lorrd +', 'lord '),
    ('^lors +', 'lord '),
    ('^losd +', 'lord '),
    ('^lose +', 'lord '),
    ('^lour +', 'lord '),
    ('^lrd +', 'lord '),
    ('^ord +', 'lord '),

    ('^earb +', 'earl '),
    ('^ear +', 'earl '),
    ('^ealr +', 'earl '),
    ('^eari +', 'earl '),
    ('^eaul +', 'earl '),
    ('^early +', 'earl '),
    ('^east +', 'earl '),
    ('^eeal +', 'earl '),
    ('^arl +', 'earl '),
    ('^eahl +', 'earl '),

    ('^dike +', 'duke '),
    ('^duek +', 'duke '),

    # Fix leading Sir
    ('^sib +', 'sir '),
    ('^sin +', 'sir '),
    ('^sit +', 'sir '),
    ('^sip +', 'sir '),
    ('^siu +', 'sir '),
    ('^sik +', 'sir '),
    ('^sat +', 'sir '),
    ('^sie +', 'sir '),
    ('^silt +', 'sir '),
    ('^sri +', 'sir '),
    ('^sr +', 'sir '),
    ('^str +', 'sir '),
    ('^air +', 'sir '),
    ('^si +', 'sir '),
    ('^sdi +', 'sir '),
    ('^slr +', 'sir '),
    
    ('^abmiral +', 'admiral '),
    ('^admtral +', 'admiral '),
    ('^admieal +', 'admiral '),
    ('^abmiral +', 'admiral '),
    ('^admiraj +', 'admiral '),
    ('^admibal +', 'admiral '),
    
    ('^admtralty +', 'admiralty '),
    ('^adralty +', 'admiralty '),
    ('^admihalty +', 'admiralty '),
    
    ('^trea-iury +', 'treasury '),
    ('^trea-treasury +', 'treasury '),
    ('^treastry +', 'treasury '),
    ('^trea sury +', 'treasury '),
    
    ('^cafiain +', 'captain '),
    ('^caftain +', 'captain '),
    ('^caitain +', 'captain '),
    ('^capain +', 'captain '),
    ('^capatain +', 'captain '),
    ('^capiain +', 'captain '),
    ('^capt +', 'captain '),
    ('^vaptain +', 'captain '),
    
    ('^col +', 'colonel '),
    ('^colconel +', 'colonel '),
    ('^coionel +', 'colonel '),
    ('^colnel +', 'colonel '),
    ('^colokel +', 'colonel '),
    ('^colonal +', 'colonel '),
    ('^colonbl +', 'colonel '),
    ('^coloxel +','colonel '),
    ('^colonl +','colonel '),
    ('^colosel +','colonel '),
    
    ('^eirst +', 'first '),
    ('^fiest +', 'first '),
    
    ('^archblsiiop +','archbishop '),
    
    ('^bistiop +', 'bishop '),
    ('^bisliop +', 'bishop '),
    ('^bisiiop +', 'bishop '),
    ('^bistiop +', 'bishop '),
    ('^lord bishop +', 'bishop '),
    
    ('^atiorney +', 'attorney'),
    ('^attornby +', 'attorney'),
    
    ('^ge neral  +', 'general '),
    ('^gen  +', 'general '),
    ('^genebal  +', 'general '),
    ('^generai  +', 'general '),
    ('^genekal  +', 'general '),
    ('^genenal  +', 'general '),
    ('^genera  +', 'general '),
    
    ('peivy', 'privy'),
    
    ('chancellor of the e xciiequer', 'chancellor of the exchequer'),
    ('chancellor of the exchequer-chequer', 'chancellor of the exchequer'),
    ('changellor of the exche-quer', 'chancellor of the exchequer'),
    ('chancellor the exchequee', 'chancellor of the exchequer'),
    ('chancellor of theexche-quer', 'chancellor of the exchequer'),
    ('chancellor of we exchequer', 'chancellor of the exchequer'),
    ('cbancellor of the exche-quer', 'chancellor of the exchequer'),
    ('^chan of the exchequer$', 'chancellor of the exchequer'),
    ('^chancellor the exchequee$', 'chancellor of the exchequer'),
    ('^chanc of the excheq$', 'chancellor of the exchequer'),
    ('^chancellok of the exche-quek$', 'chancellor of the exchequer'),
    ('^chancellor of the exchequerchequer$', 'chancellor of the exchequer'),
    ('^chanc of the exchequer$', 'chancellor of the exchequer'),
    ('^chanc of the exchequer$', 'chancellor of the exchequer'),
    ('^chancelloe of the exche-quer$', 'chancellor of the exchequer'),
    ('^chanc of tie excheq$', 'chancellor of the exchequer'),
    ('^chanckllor of the exchequer$', 'chancellor of the exchequer'),
    ('^chancellor of file exchequer$', 'chancellor of the exchequer'),
    ('^chancelloerof the exche-quer$', 'chancellor of the exchequer'),
    ('^chancelloe of the ex-chequee$', 'chancellor of the exchequer'),
    ('^chancelloe of the exchequer$', 'chancellor of the exchequer'),
    ('^chancellor of the ex-cheqner$','chancellor of the exchequer'),
    ('^chancellor ok the exchequerr$','chancellor of the exchequer'),
    ('^chancellor of tub exchequerr$','chancellor of the exchequer'),
    ('^chancellor ok thk exchequerr$','chancellor of the exchequer'),
    ('^chancellob of the exchequerr$','chancellor of the exchequer'),
    ('^chancelor of the exchequerr$','chancellor of the exchequer'),
    ('^chancelloe of the exche-quer$','chancellor of the exchequer'),
    
    ('ex-chequer', 'exchequer'),
    ('excheque', 'exchequer'),
    
    ('mrjor', 'major'),
    
    ('^chairman of ways achancellor of tub exchequerrnd means$', 'chairman'),
    ('^chairman ways and means$', 'chairman'),
    ('^chat rman of ways and means$', 'chairman'),
    ('^ghairman of ways and means$', 'chairman'),
    ('^chairman airman of ways and means$', 'chairman'),
    ('^chairman of wats and means$', 'chairman'),
    ('^chairman of ways and means$', 'chairman'),
    ('^chairman of was and means$', 'chairman'),
    ('^chairman ways and means$', 'chairman'),
    ('^chat rman of ways and means$', 'chairman'),
    ('^chairman airman of ways and means$', 'chairman'),
    
    ('^chairman of committees of ways and means$', 'chairman'),
    
    ('^chairman of committees$', 'chairman'),
    ('^chairman of commhtees$', 'chairman'),
    ('^chairman of commitmees$', 'chairman'),
    
    ('^ceairman$', 'chairman'),
    ('^mr chairman$', 'chairman'),
    ('^ceairman$', 'chairman'),
    ('^chair man$', 'chairman'),
    
    ('speaker-elect', 'speaker'),
    
    ('memberconstituencymemberconstituency', ''), # is this necessary? Seems this pattern has been removed elsewhere. Check with Alexander. 
    
    ('^a +', ''),
    ('^and +', ''),
    ('^answered by +', ''),
    ('^another +', ''),
    ('^both +', ''),
    ('^by +', ''),
    ('^here +', ''),
    
    (' on$', ''),
    (' said$', ''),
    (' ampc$', ''),
    ('ampc$', ''),
    (' i$', ''),
    (' replied$', ''),
    (' continued$', ''),
    (' presumed$', ''),
    (' resumed$', ''),
    (' resuming$', ''),
    (' also$', ''),
    (' felt$', ''),
    
    (' avar$', ' war'),

    ('irelandland', 'ireland'),

    (' tiie ', ' the '),
    (' tile ', ' the '),

    (' de ', ' of '),
    (' oe ', ' of '),
    (' uf ', ' of '),

    ('under +secretary', 'under-secretary'),
    ('under +- +secretary', 'under-secretary'),

    ('secketay +','secretary'),

    (r'lieutenant[\- ]?colonel +', ''),
    (r'lieut(.*)col', ''),
    (r'lieut', ''),

    (r'^right hon +', ''),
    (r' +observed$', ''),

    ('^general sir +', 'sir '),
    ('^mr secretary +', 'mr '),

    ('^vice-president of the council +', 'vice-president of the committee of council on education'),
    ('^vice president of the council +', 'vice-president of the committee of council on education'),
    ('^the vice president of the council +', 'vice-president of the committee of council on education'),

    ('^secretary of state for war +', ''),
    ('^president of the local government board +', ''),
    ('^president of the board of agriculture +', ''),
    ('^president of the board of trade +', ''),
    ('^secretary of state for the home department +', ''),
    ('^secretary of state for the colonies +', ''),
    ('^secretary to the treasurey +', ''),
    ('^first commissioner of works +', ''),
    ('^secretary to the admiralty +', ''),
    ('^secretary of state for india +', ''),
    ('^secretary to the local government board +', ''),
    ('^parliamentary secretary to the local government board +', ''),

    ('^-attorney', 'attorney'),
    ('^mr attorney-?general', 'attorney-general'),
    ('^she attorney', 'attorney'),
    ('^attorney-?general sir [a-z ]+', 'attorney-general'),

    # Fix hyphen surrounded by spaces.
    (' + - +', '-'),

    # Remove words preceding a title word such as (viscount, sir, mr):
    ('^.+ viscount', 'viscount'),
    ('^.+ sir ', 'sir '),
    ('^.+ mr ', 'mr '),


]

REGEX_POST_CORRECTIONS = list(map(compile_regex, REGEX_POST_CORRECTIONS))

IGNORE_KEYWORDS = (
    'member',
    'membee',
    'membek',
    'evicted tenant',
    'voice',
    'british statesman',
    'bishop',
    'archbishop',
    'this parliament'
)

IGNORE_PREFIXES = (
    'mrs ',
    'miss ',
    'a ',
    'an ',
)


def is_ignored(target: str) -> bool:
    if len(target) < 35:  # temp check: some speaker column values contain debate text
        for kw in IGNORE_KEYWORDS:
            if kw in target:
                return True
        for kw in IGNORE_PREFIXES:
            if target.startswith(kw):
                return True

    return False


def match_term(df: pd.DataFrame, date: datetime) -> pd.DataFrame:
    return df[(date >= df['start']) & (date < df['end'])]


def match_edit_distance_df(target: str,  date: datetime, df: pd.DataFrame,
                           columns: Tuple[str, str, str], speaker_dict: Dict[int, SpeakerReplacement],
                           edit_dist_func=within_distance_two) -> Tuple[Optional[str], bool]:
    start_col, end_col, search_col = columns

    match = None
    ambiguity = False

    condition = (date >= df[start_col]) & (date < df[end_col])
    query = df[condition]

    for i, alias in enumerate(query[search_col]):
        if edit_dist_func(target, alias, False):
            if match:
                match = None
                ambiguity = True
                break
            else:
                match = query.iloc[i]['corresponding_id']
                if numpy.isnan(match):
                    match = alias
                else:
                    match = speaker_dict[int(match)]
                # print('edit distance found. target=%s match=%s' % (target, repr(match)))

    return match, ambiguity


from util.jaro_distance import jaro_distance


def find_best_jaro_dist_df(target: str, df: pd.DataFrame, speechdate: datetime, curr_best, col: str, date_start_col='start',
                           date_end_col='end'):
    condition = (speechdate >= df[date_start_col]) & \
                (speechdate < df[date_end_col])
    query = df[condition]

    for row in query.itertuples(index=False):
        dist = jaro_distance(target, getattr(row, col))
        if dist > curr_best[1]:
            curr_best = [getattr(row, col), dist]
    return curr_best


def find_best_jaro_dist(target: str, alias_dict: Dict[str, List[SpeakerReplacement]],
                        honorary_title_df: pd.DataFrame,
                        lord_titles_df: pd.DataFrame,
                        aliases_df: pd.DataFrame,
                        speechdate: datetime):
    best_match = ['', 0.0]

    best_match = find_best_jaro_dist_df(target, honorary_title_df, speechdate, best_match, 'honorary_title',
                                        'start', 'end')
    best_match = find_best_jaro_dist_df(target, lord_titles_df, speechdate, best_match, 'alias')
    best_match = find_best_jaro_dist_df(target, aliases_df, speechdate, best_match, 'alias')

    for alias in alias_dict:
        dist = jaro_distance(target, alias)
        if dist > best_match[1]:
            possibles = alias_dict[alias]
            possibles = [speaker for speaker in possibles if speaker.matches(target, speechdate, cleanse=False)]
            if len(possibles) == 1:
                best_match = [alias, dist]

    return best_match


# This function will run per core.
def worker_function(inq: multiprocessing.Queue,
                    outq: multiprocessing.Queue,
                    data: DataStruct):
    from . import cleanse_string

    # Lookup optimization
    misspellings_dict = data.corrections
    alias_dict = data.alias_dict
    terms_df = data.term_df
    speaker_dict = data.speaker_dict
    honorary_title_df = data.honorary_titles_df
    office_title_dfs = data.office_position_dfs
    lord_titles_df = data.lord_titles_df
    aliases_df = data.aliases_df
    title_df = data.title_df
    holdings_df = data.holdings_df

    hitcount = 0
    matched_indexes = []
    missed_indexes = []
    ambiguities_indexes = []
    ignored_indexes = []

    fuzzy_match_indexes = []

    fuzzy_flag = 0

    MATCH_CACHE = {}
    MISS_CACHE = set()
    AMBIG_CACHE = set()
    IGNORED_CACHE = set()

    edit_distance_dict = {}  # alias -> list[speaker id's]

    extended_edit_distance_set = set()

    i = 0
    speechdate = None
    target = None
    debate_id = None
    ignored = False

    for speaker in data.speakers:
        # if len(speaker.last_name) > 8:
        #     for alias in speaker.generate_edit_distance_aliases():
        #         extended_edit_distance_set.add(alias)
        for alias in speaker.generate_edit_distance_aliases():
            edit_distance_dict.setdefault(alias, []).append(speaker.member_id)

    def postprocess(string_val: str) -> str:
        for k, v in REGEX_POST_CORRECTIONS:
            string_val = re.sub(k, v, string_val)
        return string_val.strip()

    def preprocess(string_val: str) -> str:
        # Decide whether to use the text inside parenthesis or not.

        p_match = re.search(PARENTHESIS_REGEX, string_val)
        if p_match:
            inner_string = postprocess(cleanse_string(p_match.group(1)))
            if inner_string in alias_dict:  # is this a speaker name?
                return inner_string

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

            chunk[OUTPUT_COLUMN] = chunk['speaker'].map(preprocess)

            for row in chunk.itertuples():
                fuzzy_flag = 0
                i = row[0]
                speechdate = row.speechdate
                # unmodified_target = row.speaker
                target = row.disambig_speaker
                debate_id = int(row.debate_id)

                if (target, speechdate) in MISS_CACHE:
                    missed_indexes.append(i)
                    continue
                elif (target, speechdate) in AMBIG_CACHE:
                    ambiguities_indexes.append(i)
                    continue
                elif target in IGNORED_CACHE:
                    ignored_indexes.append(i)
                    continue

                match = MATCH_CACHE.get((target, speechdate), None)
                ambiguity: bool = False
                possibles = []
                query = []

                # check if we should ignore this row.
                if not match:
                    ignored = is_ignored(target) or target in data.ignored_set

                    if ignored:
                        IGNORED_CACHE.add(target)
                        ignored_indexes.append(i)
                        continue  # continue onto the next speaker

                # if not match and not len(query):
                #     # Try honorary title
                #     condition = (speechdate >= honorary_title_df['start']) &\
                #                 (speechdate < honorary_title_df['end']) &\
                #                 (honorary_title_df['honorary_title'].str.contains(target, regex=False))
                #     query = honorary_title_df[condition]

                if not match and not len(query):
                    # try lord/viscount/earl aliases.
                    condition = (speechdate >= lord_titles_df['start']) &\
                                (speechdate < lord_titles_df['end']) &\
                                (lord_titles_df['alias'].str.contains(target, regex=False))
                    query = lord_titles_df[condition]

                if not match and not len(query):
                    # try name aliases.
                    condition = (speechdate >= aliases_df['start']) &\
                                (speechdate < aliases_df['end']) &\
                                (aliases_df['alias'].str.contains(target, regex=False))
                    query = aliases_df[condition]

                if not match and not len(query):
                    # try a lord title/alias
                    condition = (speechdate >= title_df['start']) &\
                                (speechdate < title_df['end']) &\
                                (title_df['alias'].str.contains(target, regex=False))
                    query = title_df[condition]

                # if not match and not len(query):
                #     # Try office position
                #     for position in office_title_dfs:
                #         if position in target:
                #             query = match_term(office_title_dfs[position], speechdate)
                #             break
                #         if within_distance_four(position, target, True):
                #             fuzzy_flag = 1
                #             query = match_term(office_title_dfs[position], speechdate)
                #             break

                if not match and not len(query):
                    condition = (speechdate >= holdings_df['start']) & \
                                (speechdate < holdings_df['end']) * \
                                (holdings_df['alias'].str.contains(target, regex=False))
                    query = holdings_df[condition]

                if not match:
                    query = query.drop_duplicates(subset=['corresponding_id'])
                    if len(query) == 1:
                        speaker_id = query.iloc[0]['corresponding_id']
                        if speaker_id != 'N/A' and not numpy.isnan(speaker_id):
                            # TODO: setup logging to keep track of when == n/a
                            # TODO: fix IDs missing due to being malformed entries in speakers.csv
                            # match = speaker_dict[int(speaker_id)]
                            # for now use speaker_id to ensure this counts as a match
                            try:
                                match = speaker_dict[int(speaker_id)]
                                if fuzzy_flag:
                                    fuzzy_match_indexes.append(i)
                            except KeyError as e:
                                print('failed lookup', query)
                                match = None
                                ambiguity = False

                    elif len(query) > 1:
                        ambiguity = True

                if not match:
                    possibles = alias_dict.get(target)
                    if possibles is not None:
                        possibles = [speaker for speaker in possibles if speaker.matches(target, speechdate, cleanse=False)]
                        if len(possibles) == 1:
                            match = possibles[0]
                            ambiguity = False
                        else:
                            ambiguity = True

                # Try edit distance with lord titles.
                if not match and not ambiguity:
                    match, ambiguity = match_edit_distance_df(target, speechdate, lord_titles_df,
                                                              ('start', 'end', 'alias'), speaker_dict)

                    if match: fuzzy_match_indexes.append(i)

                if not match and not ambiguity:
                    match, ambiguity = match_edit_distance_df(target, speechdate, title_df,
                                                              ('start', 'end', 'alias'), speaker_dict)
                    if match: fuzzy_match_indexes.append(i)

                # Try edit distance with honorary titles.
                # if not match and not ambiguity:
                #     match, ambiguity = match_edit_distance_df(target, speechdate, honorary_title_df,
                #                                               ('start', 'end', 'honorary_title'),
                #                                               speaker_dict)
                #     if match: fuzzy_match_indexes.append(i)

                # Try edit distance with office holdings.
                if not match and not ambiguity:
                    match, ambiguity = match_edit_distance_df(target, speechdate, holdings_df,
                                                              ('start', 'end', 'alias'),
                                                              speaker_dict, edit_dist_func=within_distance_four)
                    if match: fuzzy_match_indexes.append(i)

                # Try edit distance with MP name permutations.
                if not match and not ambiguity:
                    # Remove initials. (Even if we did consider initials, it would cause more unnecessary ambiguities.)
                    target = re.sub(r'\b[a-z]\b', '', target)
                    # Fix multiple whitespace from previous regex.
                    target = re.sub(r'  +', ' ', target)

                    possibles = []
                    for alias in edit_distance_dict:
                        # if len(possibles) > 1:
                        #     break
                        if within_distance_two(target, alias, False):
                            for speaker_id in edit_distance_dict[alias]:
                                speaker = speaker_dict[speaker_id]
                                if speaker.start_date <= speechdate <= speaker.end_date:
                                    fuzzy_flag = 1
                                    possibles.append(speaker)

                    if len(possibles) == 1:
                        match = possibles[0]
                        ambiguity = False
                        flag = 5
                        if fuzzy_flag:
                            fuzzy_match_indexes.append(i)
                    elif len(possibles) > 1:
                        ambiguity = True

                if ambiguity and possibles:
                    match = speaker_dict.get(data.inferences.get(debate_id, None), None)
                    if match not in possibles:
                        match = None
                    else:
                        ambiguity = False
                        possibles = []

                if ambiguity and possibles:
                    # Filters out duplicates.
                    speaker_ids = {speaker.member_id for speaker in possibles}
                    possibles.clear()
                    for speaker_id in speaker_ids:
                        speaker = speaker_dict[speaker_id]
                        if speaker.age_at(speechdate) < 20:
                            continue
                        if speaker.is_in_office(speechdate):
                            possibles.append(speaker)

                    if len(possibles) == 1:
                        ambiguity = False
                        match = possibles[0]
                        flag = 6

                if ambiguity:
                    match = disambiguate(target, speechdate, row.speaker_house, row.debate_id, data.speaker_dict)
                    if match == -1:
                        match = None
                    else:
                        ambiguity = False
                        match = speaker_dict.get(match, match)

                if match is not None:
                    hitcount += 1
                    if isinstance(match, SpeakerReplacement):
                        chunk.loc[i, OUTPUT_COLUMN] = match.id
                    else:
                        chunk.loc[i, OUTPUT_COLUMN] = match
                    MATCH_CACHE[(target, speechdate)] = match
                    matched_indexes.append(i)
                elif ambiguity:
                    AMBIG_CACHE.add((target, speechdate))
                    ambiguities_indexes.append(i)
                else:
                    # TODO: fix this
                    # best_guess = find_best_jaro_dist(target, alias_dict, honorary_title_df, lord_titles_df, aliases_df, speechdate)
                    # print('Best Guess for ', target, ' : ', best_guess)
                    MISS_CACHE.add((target, speechdate))
                    missed_indexes.append(i)

            outq.put((0, chunk.loc[matched_indexes, ['sentence_id', OUTPUT_COLUMN]], chunk.loc[missed_indexes, :], chunk.loc[ambiguities_indexes, :], chunk.loc[ignored_indexes, :]))
            outq.put((1, chunk.loc[fuzzy_match_indexes, ['sentence_id', 'speaker', OUTPUT_COLUMN]]))

            hitcount = 0
            del matched_indexes[:]
            del missed_indexes[:]
            del ambiguities_indexes[:]
            del ignored_indexes[:]
            del fuzzy_match_indexes[:]
