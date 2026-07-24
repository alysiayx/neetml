import logging
import pandas as pd
from rich import print
from typing import Sequence, Literal
from collections import Counter
import re

from ...utils.constants import (
    DER_COL_PREFIX,
    STUD_ID_COL,
    EXT_DATA_DIR,
    DATA_MANIFEST,
) 

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

logger = get_logger("feature_engineering")
# logger = logging.getLogger(__name__)  


def _load_ethnicity_table():
    '''
    The structure of the ethnicity table file (stored in DATA_MANIFEST['ethnicity_code']):
    {'is_meta': True,
     'files': [{'name': 'EAL Dashboard Version 2.1 Primary.xlsx',
       'sheets': [{'name': 'Ethnicity Breakdown',
         'skiprows': 4,
         'columns': {'extended_code': 'DfE Extended Code',
          'extended_categories': 'Approved Extended Categories',
          'main_code': 'DfE Main Code',
          'main_categories': 'Main Category',
          'sub_categories': 'Sub- Category'}}]}]}
    '''
    
    file_info = DATA_MANIFEST["ethnicity_code"]["files"][0]
    sheet_info = file_info["sheets"][0]

    read_path = EXT_DATA_DIR / file_info["name"]
    raw_col_map = sheet_info["columns"]

    rename_map = {
        raw_col_map["extended_code"]: "extended_code",
        raw_col_map["extended_categories"]: "extended_category",
        raw_col_map["main_code"]: "main_code",
        raw_col_map["main_categories"]: "main_category",
        raw_col_map["sub_categories"]: "sub_category",
    }

    df = pd.read_excel(
        read_path,
        sheet_name=sheet_info["name"],
        skiprows=sheet_info.get("skiprows", 0),
        usecols=list(rename_map.keys()),
    ).rename(columns=rename_map)

    df = (
        df.dropna(axis=0, how="all")
          .drop_duplicates()
          .replace({"Mixed/Duel Background": "Mixed/Dual Background"})
    )

    return df
    
def _build_mapping(df, from_col, to_col, dropna=True):
    """
    Build a dictionary mapping values from one column to another column.
    
    This helper is mainly used to create lookup dictionaries such as:
    - extended_code -> main_category
    - extended_category -> sub_category
    - main_code -> main_category

    The function checks that each value in `from_col` maps to exactly one
    unique value in `to_col`. If one key maps to multiple values, the function
    raises an error to prevent ambiguous mappings.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing the source and target mapping columns.
    
    from_col : str
        Column name used as the mapping key.
    
    to_col : str
        Column name used as the mapping value.
    
    dropna : bool, default=True
        Whether to drop rows where either `from_col` or `to_col` is missing.
        If True, rows with missing keys or missing values are removed before
        building the mapping.

    Returns
    -------
    dict
        A dictionary where keys are unique values from `from_col` and values
        are the corresponding values from `to_col`.

    Raises
    ------
    ValueError
        If one value in `from_col` maps to more than one unique value in
        `to_col`.

    Notes
    -----
    If `from_col` and `to_col` are the same column, the function returns an
    identity mapping, such as:
        {"A": "A", "B": "B"}

    """
    
    if from_col == to_col:
        s = df[from_col].dropna().drop_duplicates()
        return dict(zip(s, s))
    
    x = df[[from_col, to_col]].copy()

    if dropna:
        x = x.dropna(subset=[from_col, to_col])

    x = x.drop_duplicates()

    dup = x.groupby(from_col)[to_col].nunique()
    bad = dup[dup > 1]
    if not bad.empty:
        raise ValueError(
            f"Mapping from '{from_col}' to '{to_col}' is not one-to-one for keys: "
            f"{bad.index.tolist()[:10]}"
        )

    return x.set_index(from_col)[to_col].to_dict()

def _load_ethnicity_mappings(mapping_table: pd.DataFrame = None):
    """
    Load or build ethnicity mapping dictionaries.

    This function takes an ethnicity reference table and creates multiple
    lookup dictionaries between different ethnicity coding levels, including:
    - extended_code
    - extended_category
    - sub_category
    - main_code
    - main_category

    These mappings can then be used to convert ethnicity variables from a more
    detailed level to a broader category, or to standardise existing ethnicity
    labels.

    Parameters
    ----------
    mapping_table : pd.DataFrame, optional
        Optional ethnicity mapping table supplied directly by the user.
        If None, the function loads the default ethnicity table using
        `_load_ethnicity_table()`.
        
        Expected columns may include:
        - extended_code
        - extended_category
        - sub_category
        - main_code
        - main_category

    Returns
    -------
    dict
        A dictionary containing the original mapping table and all available
        mapping dictionaries.
        The returned dictionary contains:
        - "mapping_table" : the ethnicity reference table used
        - "ext_code_to_ext_code" : extended_code -> extended_code
        - "ext_code_to_ext_cat" : extended_code -> extended_category
        - "ext_code_to_sub_cat" : extended_code -> sub_category
        - "ext_code_to_main_cat" : extended_code -> main_category
        - "ext_code_to_main_code" : extended_code -> main_code
        - "ext_cat_to_ext_cat" : extended_category -> extended_category
        - "ext_cat_to_ext_code" : extended_category -> extended_code
        - "ext_cat_to_sub_cat" : extended_category -> sub_category
        - "ext_cat_to_main_cat" : extended_category -> main_category
        - "ext_cat_to_main_code" : extended_category -> main_code
        - "sub_cat_to_sub_cat" : sub_category -> sub_category
        - "sub_cat_to_main_code" : sub_category -> main_code
        - "sub_cat_to_main_cat" : sub_category -> main_category
        - "main_code_to_main_code" : main_code -> main_code
        - "main_code_to_main_cat" : main_code -> main_category
        - "main_cat_to_main_cat" : main_category -> main_category

        If a required column pair does not exist in the mapping table, the
        corresponding mapping value will be None.

    Raises
    ------
    ValueError
        Raised by `_build_mapping()` if a mapping is not one-to-one.
        For example, if one `extended_code` maps to multiple `main_category`
        values.

    """
    
    if mapping_table is None:
        df = _load_ethnicity_table()
    else:
        df = mapping_table.copy()

    def _maybe_build_mapping(df, from_col, to_col):
        if from_col in df.columns and to_col in df.columns:
            return _build_mapping(df, from_col, to_col)
        return None
    
    return {
        "mapping_table": df,
        
        "ext_code_to_ext_code": _maybe_build_mapping(df, "extended_code", "extended_code"),
        "ext_code_to_ext_cat": _maybe_build_mapping(df, "extended_code", "extended_category"),
        "ext_code_to_sub_cat": _maybe_build_mapping(df, "extended_code", "sub_category"),
        "ext_code_to_main_cat": _maybe_build_mapping(df, "extended_code", "main_category"),
        "ext_code_to_main_code": _maybe_build_mapping(df, "extended_code", "main_code"),
        
        "ext_cat_to_ext_cat": _maybe_build_mapping(df, "extended_category", "extended_category"),
        "ext_cat_to_ext_code": _maybe_build_mapping(df, "extended_category", "extended_code"),
        "ext_cat_to_sub_cat": _maybe_build_mapping(df, "extended_category", "sub_category"),
        "ext_cat_to_main_cat": _maybe_build_mapping(df, "extended_category", "main_category"),
        "ext_cat_to_main_code": _maybe_build_mapping(df, "extended_category", "main_code"),
        
        "sub_cat_to_sub_cat": _maybe_build_mapping(df, "sub_category", "sub_category"),
        "sub_cat_to_main_code": _maybe_build_mapping(df, "sub_category", "main_code"),
        "sub_cat_to_main_cat": _maybe_build_mapping(df, "sub_category", "main_category"),
        
        "main_code_to_main_code": _maybe_build_mapping(df, "main_code", "main_code"),
        "main_code_to_main_cat": _maybe_build_mapping(df, "main_code", "main_category"),
        
        "main_cat_to_main_cat": _maybe_build_mapping(df, "main_category", "main_category"),
    }

def _add_multi_ethnic_features(
    input_data: pd.DataFrame, 
    stud_id_col: str = STUD_ID_COL, 
    check_level_col: str = None, 
    prefix=DER_COL_PREFIX
):
    """
    Derive curated ethnicity and multi-ethnicity conflict features.

    It checks whether each student has more than one substantive
    ethnicity value in `check_level_col`. Non-substantive values such as
    "refused", "unknown", and "not obtained" are excluded before counting
    ethnicity conflicts.

    If a student has exactly one substantive ethnicity value, that value is
    stored in the curated ethnicity column. If a student has multiple
    substantive ethnicity values, the curated ethnicity column is set to NA
    to avoid assigning a misleading ethnicity category.

    Parameters
    ----------
    input_data : pd.DataFrame
        Input student-level or student-year-level dataset.

    stud_id_col : str, default=STUD_ID_COL
        Column identifying each student.

    check_level_col : str, default=None
        Ethnicity column used to check conflicts and derive the curated
        ethnicity value.

    prefix : str, default=DER_COL_PREFIX
        Prefix added to the derived column names. An underscore is added
        automatically if not already present.

    Returns
    -------
    pd.DataFrame
        A copy of `input_data` with three additional columns:
        - `{prefix}ethnicity`
        - `{prefix}ethnicity_conflict_n`
        - `{prefix}ethnicity_conflict_flag`

        `{prefix}ethnicity_conflict_n` gives the number of unique substantive
        ethnicity values per student.

        `{prefix}ethnicity_conflict_flag` is True when a student has more than
        one substantive ethnicity value.

        `{prefix}ethnicity` contains the curated ethnicity value when there is
        exactly one substantive value, and NA otherwise.
    """
    df = input_data.copy()
    prefix = prefix if prefix.endswith("_") else prefix + "_"
    
    NON_SUBSTANTIVE = {
        "refused",
        "unknown",
        "not obtained",
        "not known",
        "information not yet obtained",
        "missing",
        "refu",
        "nobt",
    }
    
    df_check = df[[stud_id_col, check_level_col]].dropna(subset=[check_level_col])
    
    mask = (
        df_check[check_level_col]
        .astype("object")
        .str.strip()
        .str.lower()
        .isin(NON_SUBSTANTIVE)
    )
    df_check_valid = df_check.loc[~mask]
    
    n_per_student = (
        df_check_valid
        .groupby(stud_id_col)[check_level_col]
        .nunique()
    )
    
    col_curated = f"{prefix}curated"
    col_conflict_n = f"{prefix}conflict_n"
    col_conflict_flag = f"{prefix}conflict_flag"

    df[col_conflict_n] = df[stud_id_col].map(n_per_student).fillna(0).astype(int)
    df[col_conflict_flag] = df[col_conflict_n].gt(1)
    
    # if there are multiple conflicting entries, we set the curated column to NA to avoid misleading information. 
    ethnic_map = df_check_valid.drop_duplicates().drop_duplicates(subset=[stud_id_col], keep=False).set_index(stud_id_col)[check_level_col].to_dict()
    df[col_curated] = df[stud_id_col].map(ethnic_map)
    
    check_df = (
        df[[stud_id_col, col_curated]]
        .dropna(subset=[col_curated])
        .drop_duplicates()
    )

    n_curated_per_student = check_df.groupby(stud_id_col)[col_curated].nunique()
    bad_ids = n_curated_per_student[n_curated_per_student > 1].index

    assert bad_ids.empty, (
        "There are still students with multiple curated ethnicity entries after the conflict check. "
        "Please check the derivation logic.\n\n"
        "Examples:\n"
        f"{df.loc[df[stud_id_col].isin(bad_ids), [stud_id_col, check_level_col, col_curated, col_conflict_n, col_conflict_flag]].head(20)}"
    ) 
    
    count_df = df[[stud_id_col, col_conflict_n, col_conflict_flag]].drop_duplicates().sort_values(stud_id_col).reset_index(drop=True)
    
    summary = (
        count_df[[col_conflict_n, col_conflict_flag]]
        .value_counts(dropna=False)
        .rename_axis(["multi_n", "multi_flag"])
        .reset_index(name="count")
        .sort_values(["multi_n", "multi_flag"])
        .reset_index(drop=True)
    )

    logger.debug("Value counts of multi-ethnicity flags:\n%s", summary)
    
    n_stud_non_substantive = df_check[mask][stud_id_col].nunique()
    logger.debug(f"{n_stud_non_substantive} out of {df[stud_id_col].nunique()} students have non-substantive ethnicity entries.")
    
    logger.info(
        f"Derived column for multi-ethnicity features ('{col_conflict_n}' and '{col_conflict_flag}') based on '{check_level_col}'. \n \
        '{col_curated}' contains the curated ethnicity category based on '{check_level_col}', with conflicting entries and entries only with non-substantive values set to NA. \n \
        NOTE: 'Refused/Unknown/Not obtained' categories are treated as non-substantive and are excluded from the multi-ethnicity conflict check."
    )
    
    # logger.info(
    #     f"Derived column for multi-ethnicity features ('{col_conflict_n}' and '{col_conflict_flag}') based on '{check_level_col}'. \n \
    #     NOTE: 'Refused/Unknown/Not obtained' categories are treated as non-substantive and are excluded from the multi-ethnicity conflict check."
    # )

    return df

def _clean_school_type(x): # temp solution
    """
    Standardise school type labels
    """

    if pd.isna(x):
        return pd.NA

    s = str(x).strip().lower()
    s = re.sub(r"[\-_]+", " ", s)
    s = re.sub(r"\s+", " ", s)

    # Short codes
    code_map = {
        "cy": "Community School",
        "fd": "Foundation School",
        "va": "Voluntary Aided School",
        "vc": "Voluntary Controlled School",
    }

    if s in code_map:
        return code_map[s]

    # Academy
    if "academy" in s:
        is_converter = "converter" in s
        is_sponsor = "sponsor" in s or "sponsored" in s
        is_special = "special" in s
        is_ap = "alternative provision" in s or re.search(r"\bap\b", s)

        if is_converter and is_special:
            return "Academy - Converter Special"
        if is_sponsor and is_special:
            return "Academy - Sponsor Led Special"
        if is_converter:
            return "Academy - Converter"
        if is_sponsor:
            return "Academy - Sponsor Led"
        if is_special:
            return "Academy - Special School"
        if is_ap:
            return "Academy - Alternative Provision"

        return "Academy"

    # Free school
    if "free school" in s or "free schools" in s:
        if "alternative provision" in s:
            return "Free School - Alternative Provision"
        if "utc" in s or "university technical college" in s:
            return "Free School - UTC"
        if "16" in s or "19" in s:
            return "Free School - 16-19"
        if "special" in s:
            return "Free School - Special"
        return "Free School - Mainstream"

    # UTC written without Free School
    if "university technical college" in s:
        return "Free School - UTC"

    # Community
    if "community" in s:
        if "special" in s:
            return "Community Special School"
        return "Community School"

    # Foundation
    if "foundation" in s:
        if "special" in s:
            return "Foundation Special School"
        return "Foundation School"

    # Voluntary aided / controlled
    if "voluntary aided" in s:
        return "Voluntary Aided School"

    if "voluntary controlled" in s:
        return "Voluntary Controlled School"

    # Independent
    if "independent" in s:
        if "special" in s:
            return "Independent Special School"
        return "Independent School"

    # Non-maintained special
    if "non maintained" in s or "non maintained special" in s:
        return "Non-Maintained Special School"

    # Pupil referral / alternative provision
    if "pupil referral" in s:
        return "Pupil Referral Unit"

    if "alternative provision" in s:
        return "Alternative Provision"

    # Further education / colleges
    if (
        "further education" in s
        or "general further education college" in s
        or "agriculture and horticulture college" in s
    ):
        return "Further Education College"

    return str(x).strip()

def _add_cum_features(
    df: pd.DataFrame,
    id_col: str,
    time_col: str,
    list_col: str,
    prefix: str,
    features: Sequence[str] = ("hist", "n_uniq", "main", "main_n")
):
    """
    Add cumulative history features for a list-like column.

    Creates:
    - {prefix}_hist: cumulative unique values up to current time
    - {prefix}_n_uniq: number of cumulative unique values
    - {prefix}_main: most frequent value up to current time; if tied and current year has one value, use the current value
    - {prefix}_main_n: frequency of the most frequent value
    """
    
    valid_features = {"hist", "n_uniq", "main", "main_n"}
    features = tuple(features)
    features = valid_features.intersection(set(features))
    
    if features:
        logger.debug(f"Following features will be generated: {features}")
    else:
        raise ValueError(f"Invalid features.")

    d = df.copy()
    id_col = [id_col] if isinstance(id_col, str) else id_col
    time_col = [time_col] if isinstance(time_col, str) else time_col
    
    d["_ord"] = range(len(d))
    d = d.sort_values(id_col + time_col)

    rows = []

    for _, g in d.groupby(id_col, sort=False):
        seen = set()
        cnt = Counter() # Initialize counter for cumulative frequencies

        for _, r in g.iterrows():
    
            vals = r[list_col]

            if isinstance(vals, pd.Series):
                vals = vals.dropna().tolist()
            elif not isinstance(vals, (list, tuple, set, frozenset)):
                vals = [vals]
          
            # find all non-empty values
            vals = sorted({
                str(x).strip()
                for x in vals
                if pd.notna(x) and str(x).strip()
            })
            
            if not vals:
                continue
         
            # update cumulative history and frequency counts.
            seen.update(vals)
            cnt.update(vals)

            if not cnt:
                main, main_n = pd.NA, 0
            else:
                max_n = max(cnt.values())  # highest frequency count among values seen so far
                top_vals = [k for k, v in cnt.items() if v == max_n]  # values tied for the highest frequency count

                # If there is a tie and the current year has exactly one value,
                # use the current year's value as the main value.
                if len(top_vals) > 1 and len(vals) == 1:
                    main = vals[0]
                    main_n = cnt[main]
                else:
                    main = sorted(top_vals)[0]
                    main_n = max_n

            row = {"_ord": r["_ord"]}

            feat_vals = {
                "hist": tuple(sorted(seen)),
                "n_uniq": len(seen),
                "main": main,
                "main_n": main_n,
            }

            row.update({
                f"{prefix.rstrip('_')}_{k.lstrip('_')}": v
                for k, v in feat_vals.items()
                if k in features
            })

            rows.append(row)

    feat = pd.DataFrame(rows)
    
    hist_col = f"{prefix}_hist"
    if hist_col in feat.columns: # replace empty tuple with pd.NA
        feat[hist_col] = feat[hist_col].map(
            lambda x: pd.NA if isinstance(x, tuple) and len(x) == 0 else x
        )
    
    df_new = (
        d.merge(feat, on="_ord", how="left")
         .sort_values("_ord")
         .drop(columns="_ord")
    )

    return df_new

def _add_state_features(
    df: pd.DataFrame,
    id_col: str,
    time_cols: list,
    state_cols: Sequence[str],
    prefix: str = "sch",
    threshold: int = 2,
) -> pd.DataFrame:
    """
    Add cumulative school state change features.
    
    A change is counted if either:
    1. At least `threshold` state columns changed compared with previous year.
    2. At least `threshold` state columns contain multiple values within current year.
    """
    prefix = f"{prefix}_" if not prefix.endswith('_') else prefix
    
    out = df.copy()
    
    out = out.sort_values([id_col] + time_cols)

    between_flags = [] # list of pd.Series
    within_flags = []

    for col in state_cols:
        # get previous year's data
        prev = out.groupby(id_col, sort=False)[col].shift(periods=1)

        # Between-year change: current state differs from previous state
        # only check this if both values are non-empty
        between_changed = (
            prev.notna()
            & out[col].notna()
            # & out[col].ne(prev) # Direct inequality can double count within-year changes. If current state is a subset of the previous year's state set, it is not a new change. Use the subset/new-value check below instead.
            & pd.Series(
                [
                    not set(cur if isinstance(cur, (list, tuple, set, frozenset)) else ())
                    .issubset(set(prv if isinstance(prv, (list, tuple, set, frozenset)) else ()))
                    for cur, prv in zip(out[col], prev)
                ],
                index=out.index,
            )
        )

        between_flags.append(between_changed.astype("int8")) # One flag per row; len(between_flags) == len(state_cols), and each flag has length len(out).
        
        # Within-year change: current state has multiple values
        within_changed = out[col].apply(
            lambda x: isinstance(x, (list, tuple, set, frozenset)) and len(x) > 1
        )

        within_flags.append(within_changed.astype("int8"))

    out["_n_changed_parts"] = sum(between_flags) # row-wise sum
    out["_n_multi_parts"] = sum(within_flags)

    out[f"{prefix}changed"] = (
        out["_n_changed_parts"].ge(threshold)
        | out["_n_multi_parts"].ge(threshold)
    ).astype("int8")

    out[f"{prefix}n_chg"] = (
        out.groupby(id_col, sort=False)[f"{prefix}changed"]
        .cumsum()
        .astype("int64")
    )

    out[f"{prefix}ever_changed"] = (
        out[f"{prefix}n_chg"].gt(0)
    ).astype("int8")

    out.drop(columns=["_n_changed_parts", "_n_multi_parts"], inplace=True)

    return out