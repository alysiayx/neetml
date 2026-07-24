import logging
import pprint
from math import log
from pickletools import int4
import pandas as pd
import numpy as np
import janitor
import os
import requests
import zipfile
import io
from pathlib import Path
import cgi
from rich import print
import yaml
from typing import Literal, Union, Sequence, Any
from functools import reduce

from ...utils.misc import (
    styled_print,
    load_dataframe,
    collapse_cols
)

from ...utils.constants import (
    ExtRefs,
    CSP_CONFIGS,
    EXT_COL_PREFIX,
    DER_COL_PREFIX,
    DATA_PATHS,
    MergeMetadata,
    STUD_ID_COL,
    SRC_META_DIR,
    EXT_DATA_DIR,
    DATA_MANIFEST,
) 

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from ._derivation_utils import (
    _add_multi_ethnic_features,
    _load_ethnicity_mappings,
    _clean_school_type,
    _add_cum_features,
    _add_state_features
)

logger = get_logger("feature_engineering")
# logger = logging.getLogger(__name__)  


def add_ethnicity_levels(
    input_data: pd.DataFrame,
    ethnic_col: str,
    mapping_table: pd.DataFrame = None,
    prefix: str = DER_COL_PREFIX,
    overwrite: bool = False,
):
    
    if mapping_table is None:
        styled_print("Using default ethnicity mapping table from metadata", colour="yellow")
        ethnic_map = _load_ethnicity_mappings()
    else:
        styled_print("Using user provided ethnicity mapping table", colour="yellow")
        
        raw_col_map = DATA_MANIFEST["ethnicity_code"]["files"][0]["sheets"][0]["columns"]
        
        if raw_col_map.keys() not in mapping_table.columns:
            raise ValueError(
                f"Provided mapping table is missing required columns. Expected at least: "
                f"{list(raw_col_map.values())}"
            )

        ethnic_map = _load_ethnicity_mappings(mapping_table)
        
    df = input_data.copy()
    
    def find_matching_column(code):
        matched = []
        for col in ethnic_map["mapping_table"].columns:
            if code.lower() in ethnic_map["mapping_table"][col].astype(str).str.lower().values:
                matched.append(col)
        return ', '.join(matched) if matched else 'Unmatched'
    
    ethnicity_counts = df[ethnic_col].value_counts().rename_axis('code').reset_index(name='count')
    ethnicity_counts['source'] = ethnicity_counts['code'].apply(find_matching_column)

    logger.debug(f"Number of unique ethnicity codes in {ethnic_col}: {ethnicity_counts['code'].nunique()}")
    logger.debug(f"Value counts of {ethnic_col}: \n{ethnicity_counts['source'].value_counts()}\n")
    logger.debug(f"Unmatched codes: {ethnicity_counts[ethnicity_counts['source'] == 'Unmatched']}")
    
    prefix = prefix if prefix.endswith("_") else prefix + "_"
    
    s = df[ethnic_col]
    s = s.astype("object").where(s.isna(), s.astype("object").str.strip().str.lower())

    for k, v in ethnic_map.items():
        if k != "mapping_table" and v is not None:
            ethnic_map[k] = {str(key).strip().lower(): val for key, val in v.items()}
    
    priority = ["ext_code", "ext_cat", "sub_cat", "main_code", "main_cat"] # from fine-grained to coarse-grained
    
    for level in priority[::-1]: # from coarse-grained to fine-grained
        # col_name = f"{prefix}ethnicity_{level}"
        col_name = f"{prefix}{level}"
        if col_name in df.columns:
            logger.warning(f"Column '{col_name}' already exists in the dataframe {'and will be overwritten' if overwrite else 'and will not be overwritten'}.")
        
        maps = [
            ethnic_map.get(f"{src}_to_{level}")
            for src in priority
            if ethnic_map.get(f"{src}_to_{level}") is not None
        ]
        
        if not maps:
            logger.warning(f"No mapping available to derive '{col_name}'. Skipping this level.")
            continue
        else:
            logger.debug(f"Deriving '{col_name}' using mappings: {[f'{src}_to_{level}' for src in priority if ethnic_map.get(f"{src}_to_{level}") is not None]}")
        
        out = None
        for m in maps:
            cur = s.map(m)
            out = cur if out is None else out.fillna(cur)
        
        df[col_name] = out.astype("category")

    # new_cols = [col for col in df.columns if col.startswith(prefix + 'ethnicity_') and col != ethnic_col]
    new_cols = [col for col in df.columns if col.startswith(prefix) and col != ethnic_col]
    logger.info(f"Following ethnicity levels have been derived from '{ethnic_col}': {new_cols}")
    
    # validate (temp check)
    
    # left = (df[[f"{prefix}ethnicity_ext_code", f"{prefix}ethnicity_ext_cat", f"{prefix}ethnicity_main_code",
    #             f"{prefix}ethnicity_sub_cat", f"{prefix}ethnicity_main_cat"]]
    #         .dropna(subset=[f"{prefix}ethnicity_ext_code"]).drop_duplicates()
    #         .sort_values(f"{prefix}ethnicity_ext_code").reset_index(drop=True))
    # right = (ethnic_map["mapping_table"]
    #          .loc[lambda x: x["extended_code"].isin(left[f"{prefix}ethnicity_ext_code"].unique()),
    #               ["extended_code", "extended_category", "main_code", "sub_category", "main_category"]]
    #          .drop_duplicates().sort_values("extended_code").reset_index(drop=True))
    
    # assert (left.to_numpy() == right.to_numpy()).all() 
    
    return df, ethnic_map

def derive_ethnic_features(
    input_data: pd.DataFrame,
    ethnic_col: str = None,
    prefix: str = DER_COL_PREFIX,
    check_level: Literal["main_cat", "main_code", "sub_cat", "ext_cat", "ext_code", False] = "main_cat",
    stud_id_col: str = STUD_ID_COL,
    time_cols: str | Sequence[str] | None = None,
    return_features: bool = False,
):
    
    logger.info("Deriving Ethnicity Levels.....")
    
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
   
    if ethnic_col is None:
        ethnic_col = next((col for col in df.columns if "ethnic" in col.lower()), None)
        if ethnic_col is None:
            raise ValueError("No column containing 'ethnic' found in the dataframe. Please specify the 'ethnic_col' parameter.")
    
    df = input_data.copy(deep=True)
    
    is_non_substantive = df[ethnic_col].astype(str).str.strip().str.lower().isin(NON_SUBSTANTIVE)
    df = df[~is_non_substantive]
    
    df_new, ethnic_map = add_ethnicity_levels(
        input_data=df,
        ethnic_col=ethnic_col,
        prefix=prefix,
    )
    
    # ethnic_map["mapping_table"].to_excel("ethnicity_mapping_table.xlsx", index=False)
    
    if check_level:
        logger.info(f"Deriving multi-ethnicity features based on specified check level: '{check_level}'")
        
        prefix = prefix if prefix.endswith("_") else prefix + "_"
        
        # ethnic_check_col = f"{prefix}ethnicity_{check_level}"
        ethnic_check_col = f"{prefix}{check_level}"
        
        # valid_ethnic_check_col = [col for col in df_new.columns if col.startswith(prefix + 'ethnicity_')]
        valid_ethnic_check_col = [col for col in df_new.columns if col.startswith(prefix)]
        
        if ethnic_check_col not in df_new.columns:
            logger.warning(
                f"Specified check level '{check_level}' does not have a corresponding derived column '{ethnic_check_col}' in the output. \
                {'Available derived columns are: {valid_ethnic_check_col}' if valid_ethnic_check_col else 'No derived ethnicity columns are present in the output.'}, we will proceed with '{ethnic_col}'."
            )
            ethnic_check_col = ethnic_col
        else:
            logger.debug(f"Multi-ethnic features will be derived based on '{ethnic_check_col}'.")
        
        df_new = _add_multi_ethnic_features(
            input_data=df_new,
            stud_id_col=stud_id_col,
            check_level_col=ethnic_check_col,
            prefix=prefix
        )
    
    main_cat_col = [col for col in df_new.columns if col.endswith("main_cat")]
    
    if time_cols is not None:
        if len(main_cat_col) >= 1:
            
            time_cols = [time_cols] if isinstance(time_cols, str) else list(time_cols)
            
            df_main = df_new[[stud_id_col] + time_cols + main_cat_col].dropna(subset=main_cat_col).drop_duplicates()
            
            df_main = _add_cum_features(
                df_main,
                id_col=stud_id_col,
                time_col=time_cols,
                list_col=main_cat_col,
                prefix=prefix,
                features=["main"],
            )                
            df_new = df_new.merge(df_main.drop(columns=main_cat_col), on=[stud_id_col] + time_cols, how='left').drop_duplicates()
    
    added_cols = set(df_new.columns) - set(input_data.columns)
    if len(added_cols) > 0:
        format_added_cols = pprint.pformat(added_cols, indent=4, compact=True)
        logger.info(
            f"Following columns have been added to the data: \n{format_added_cols}\n"
        )
    
    log_line_break(logger)
    
    if return_features:
        original_cols = [col for col in df.columns if col != stud_id_col]
        derived_cols = [col for col in df_new.columns if col not in original_cols and col != stud_id_col]
        df_features = df_new[[stud_id_col] + derived_cols].drop_duplicates()
        
        # assert df_features[stud_id_col].is_unique, "Derived features contain duplicate student IDs. Please check the derivation logic."
        return df_features
    else:
        return df_new

def derive_gender_features(
    input_data: pd.DataFrame,
    gender_cols: list = None,
    time_cols: list = [],
    prefix: str = DER_COL_PREFIX,
    stud_id_col: str = STUD_ID_COL,
    return_features: bool = False,
):
    logger.info("Deriving Gender Features.....")
    
    time_cols = [time_cols] if isinstance(time_cols, str) else list(time_cols)
    
    group_cols = [stud_id_col] + time_cols
    
    df = input_data.copy(deep=True)
    
    if isinstance(gender_cols, str):
        gender_cols = [gender_cols]
    
    # prefix = prefix if prefix.endswith("_") else prefix + "_"
    
    # new_gender_col = f"{prefix}gender"
    new_gender_col = prefix
    
    df_gender = collapse_cols(
        df=df,
        group_cols=group_cols,
        value_cols=gender_cols,
        out_col=new_gender_col
    )
    
    # cheeck if there are any conflicts among the gender columns
    df_conflict = df_gender[df_gender[new_gender_col].map(len).gt(1)]
    
    if df_conflict.shape[0] > 1:
        logger.debug(f"Conflicts detected among gender columns: {gender_cols}, counts for {df_conflict[stud_id_col].nunique()} students. \nSample of conflicting entries:\n{df_conflict.head(10)}")
    
    
    missing_before = df_gender.loc[df_gender[new_gender_col].isna(), stud_id_col].nunique()
    
    if time_cols:
        df_gender = _add_cum_features(
            df_gender,
            id_col=stud_id_col,
            time_col=time_cols,
            list_col=new_gender_col,
            prefix=prefix,
            features=["main"],
        )    

    df_gender[new_gender_col] = df_gender[new_gender_col].map(
        lambda x: x[0] if isinstance(x, tuple) and len(x) == 1 else pd.NA
    )
    
    missing_after = df_gender.loc[df_gender[new_gender_col].isna(), stud_id_col].nunique()

    logger.debug("Missing students in '%s': before=%d, after=%d.",new_gender_col, missing_before, missing_after)
        
    df_new = df.merge(df_gender.dropna(subset=[new_gender_col]).drop_duplicates(), on=group_cols, how='left')
    
    gender_nunique = (
        df_new[[stud_id_col, new_gender_col]]
        .drop_duplicates()
        .dropna(subset=[new_gender_col])
        .groupby(stud_id_col)[new_gender_col]
        .nunique()
    )

    bad_ids = gender_nunique.index[gender_nunique.gt(1)]

    assert len(bad_ids) == 0, (
        "There are still students with multiple gender entries after the conflict check. "
        f"Sample:\n{df_new.loc[df_new[stud_id_col].isin(bad_ids), [stud_id_col, new_gender_col]].drop_duplicates().head(20)}"
    )
    
    logger.info(f"Derived gender column: '{new_gender_col}' based on gender colums: '{gender_cols}'. \nConflicting entries in the '{new_gender_col}' have been set to NA in the derived gender column to avoid misleading information.")
    
    added_cols = set(df_new.columns) - set(input_data.columns)
    if len(added_cols) > 0:
        format_added_cols = pprint.pformat(added_cols, indent=4, compact=True)
        logger.info(
            f"Following columns have been added to the data: \n{format_added_cols}\n"
        )
    
    log_line_break(logger)
    
    if return_features:
        df_features = df_new[[stud_id_col, new_gender_col]].drop_duplicates()
        # assert df_features[stud_id_col].is_unique, "Derived features contain duplicate student IDs. Please check the derivation logic."
        return df_features
    else:
        return df_new

def derive_school_features(
    input_data: pd.DataFrame,
    urn_cols: str | Sequence[str] | None = None,
    pcd_cols: str | Sequence[str] | None = None,
    type_cols: str | Sequence[str] | None = None,
    gender_type_cols: str | Sequence[str] | None = None,
    stud_id_col: str = STUD_ID_COL,
    time_cols: str | Sequence[str] | None = None,
    clean_type: bool = True,
    prefix: str = DER_COL_PREFIX,
    features: Sequence[str] = ("hist", "n_uniq", "main", "main_n", "state_chg"),
    state_threshold: int = 2,
    return_type_mappings: bool = True,
    return_dup_ids: bool = True,
) -> pd.DataFrame | tuple[Any]:
    
    """

    Derive longitudinal school history features.

    Parameters
    ----------
    input_data : pd.DataFrame
        Input student-level longitudinal dataframe. It may contain multiple rows
        per student and year.

    urn_cols : str | Sequence[str] | None, default None
        URN columns used to identify schools. Multiple columns are collapsed into
        one yearly sorted tuple per student-year.

    pcd_cols : str | Sequence[str] | None, default None
        Postcode columns used to identify school locations. Multiple columns are
        collapsed into one yearly sorted tuple per student-year.

    type_cols : str | Sequence[str] | None, default None
        School type columns. Multiple columns are collapsed into one yearly
        sorted tuple per student-year.

    stud_id_col : str, default STUD_ID_COL
        Student ID column.

    time_col : str | Sequence[str] | None, default None
        Time ordering column, for example "_year_group". Features are calculated
        up to and including each value of this column.

    clean_type : bool, default True
        Whether to standardise school type values before deriving features.

    prefix : str, default DER_COL_PREFIX
        Prefix added to derived feature names.

    features : Sequence[str], default ("hist", "n_uniq", "main", "main_n", "state_chg", "state_n_chg")
        Features to return.
        
        Available options:
        - "hist": cumulative unique values up to current year
        - "n_uniq": number of cumulative unique values
        - "main": most frequent value up to current year
        - "main_n": frequency of the main value
        - "state_chg": whether school state changed in the current year

    state_threshold : int, default 2
        Number of changed school state components required to count as a state
        change. For example, with URN, postcode and school type, threshold=2
        means at least two of the three must change.

    return_type_mappings : bool, default True
        Whether to return the raw-to-clean school type mapping table.

    return_dup_ids : bool, default True
        Whether to return student IDs with multiple values in at least one input
        URN/postcode/type column.

    Returns
    -------
    pd.DataFrame | tuple[Any]
        If no extra outputs are requested, returns the feature dataframe.
        
        If return_type_mappings or return_dup_ids is True, returns a tuple:
        - first item: feature dataframe
        - optional item: school type mapping dataframe
        - optional item: duplicate/conflict student IDs
    """
    
    logger.info("Deriving School Features.....")
    
    df = input_data.copy(deep=True)
    
    urn_cols = [urn_cols] if isinstance(urn_cols, str) else list(urn_cols)
    pcd_cols = [pcd_cols] if isinstance(pcd_cols, str) else list(pcd_cols)
    type_cols = [type_cols] if isinstance(type_cols, str) else list(type_cols)
    gender_type_cols = [gender_type_cols] if isinstance(gender_type_cols, str) else list(gender_type_cols)
    time_cols = [time_cols] if isinstance(time_cols, str) else list(time_cols)
    group_cols = [stud_id_col] + time_cols
    
    prefix = f"{prefix}_" if not prefix.endswith('_') else prefix
    postfix = "_latest"
    
    if clean_type and type_cols:
        logger.warning(
            "Original values will be overwritten after standardisation for columns:\n%s",
            pprint.pformat(type_cols, indent=4, compact=True),
        )       
        
        if return_type_mappings: # if want to check the standardised values are correct
            set_all = set(df[type_cols].stack(dropna=True).unique())
            
            type_map_df = (
                pd.Series(sorted(set_all), name="raw")
                  .to_frame()
                  .assign(clean=lambda x: x["raw"].apply(_clean_school_type))
                  .assign(changed=lambda x: x["raw"].ne(x["clean"]))
                  .sort_values(["clean", "raw"])
                  .reset_index(drop=True)
            )
        
        for col in type_cols:
            # m = (
            #     df[col].drop_duplicates()
            #     .to_frame("raw")
            #     .assign(clean=lambda x: x["raw"].apply(_clean_school_type))
            # )

            # m["changed"] = (
            #     m["raw"].astype("string").fillna("<NA>")
            #     .ne(m["clean"].astype("string").fillna("<NA>"))
            # )

            # logger.debug(
            #     "School type mapping for column '%s':\n%s\n",
            #     col,
            #     m.to_string(index=False),
            # )
            
            # df[f"{col}_std"] = df[col].apply(_clean_school_type)
            df[col] = df[col].apply(_clean_school_type)

    cols = urn_cols + pcd_cols + type_cols + gender_type_cols

    multi_ids_by_col = {
        c: df.loc[df.groupby(stud_id_col)[c].transform("nunique").gt(1),stud_id_col,].unique()
        for c in cols
    }

    empty_ids_by_col = {
        c: df.loc[df.groupby(stud_id_col)[c].transform("count").eq(0),stud_id_col,].unique()
        for c in cols
    }

    for c in cols:
        logger.debug("Found %d students with more than one unique value in column '%s'.",len(multi_ids_by_col[c]),c,)
        logger.debug("Found %d students without values in column '%s'.",len(empty_ids_by_col[c]),c,)
    
    dup_stud_ids = set().union(*multi_ids_by_col.values())

    logger.info(
        "Found potential %d out of %d students with more than one unique URN/postcode/school type value in at least one column.",
        len(dup_stud_ids),
        df[stud_id_col].nunique(),
    )
    
    # # takes a longer time
    # urn_set = (
    #     df.groupby([stud_id_col, time_col])[urn_cols]
    #       .agg(lambda x: sorted(set(x.dropna().astype(str))))
    #       .agg(lambda row: sorted(set().union(*row)), axis=1)
    #       .reset_index(name="urn_set")
    # )

    specs = [
        (urn_cols, f"{prefix}urn{postfix}", f"{prefix}urn"),
        (pcd_cols, f"{prefix}postcode{postfix}", f"{prefix}postcode"),
        (type_cols, f"{prefix}type{postfix}", f"{prefix}type"),
        (gender_type_cols, f"{prefix}gender_type{postfix}", f"{prefix}gender_type")
    ]

    # Build school-level feature table from collapsed URN/postcode/type columns
    df_school = reduce(
        lambda l, r: l.merge(r, how="outer", on=group_cols),
        [
            collapse_cols(df, group_cols, value_cols, out_col=latest)
            for value_cols, latest, _ in specs
        ],
    )

    for _, latest, feat_prefix in specs:
        df_school = _add_cum_features(
            df_school,
            id_col=stud_id_col,
            time_col=time_cols,
            list_col=latest,
            prefix=feat_prefix,
            features=features,
        )
        
    df_school.dropna(axis=1, how='all', inplace=True)
    
    if "state_chg" in features:
        logger.debug("Features regarding school status change will be derived.")
        df_school = _add_state_features(
            df_school,
            id_col=stud_id_col,
            state_cols=[s[1] for s in specs],
            time_cols=time_cols,
            threshold=state_threshold,
            prefix=f"{prefix}state"
        )    
    
    df = df.merge(df_school, on=group_cols, how='left')

    outputs = [df] + [
        obj for flag, obj in [
            (return_type_mappings, type_map_df),
            (return_dup_ids, dup_stud_ids),
        ]
        if flag
    ]
    
    added_cols = set(df.columns) - set(input_data.columns)
    if len(added_cols) > 0:
        format_added_cols = pprint.pformat(added_cols, indent=4, compact=True)
        logger.info(f"Following columns have been added to the data: \n{format_added_cols}")
        
    log_line_break(logger)

    return df if len(outputs) == 1 else tuple(outputs)

def derive_language_features(
    input_data: pd.DataFrame,
    language_col: str = None,
    prefix: str = DER_COL_PREFIX,
    stud_id_col: str = STUD_ID_COL,
    time_cols: str | Sequence[str] | None = None,
    features: Sequence[str] = ("hist", "n_uniq", "main", "main_n"),
):
    logger.info("Deriving Language Features.....")
    
    NON_SUBSTANTIVE = {
        "refused",
        "unknown",
        "not obtained",
        "not known",
        "information not yet obtained",
        "missing",
        "ref",
        "not",
    }
    
    df = input_data.copy(deep=True)
    
    time_cols = [time_cols] if isinstance(time_cols, str) else list(time_cols)
    group_cols = [stud_id_col] + time_cols
    
    prefix = f"{prefix}_" if not prefix.endswith('_') else prefix
    
    df_lan = df[group_cols + [language_col]].dropna(subset=[language_col]).drop_duplicates()
    
    is_non_substantive = df_lan[language_col].astype(str).str.strip().str.lower().isin(NON_SUBSTANTIVE)
    df_lan = df_lan[~is_non_substantive]
    
    df_lan = _add_cum_features(
        df_lan,
        id_col=stud_id_col,
        time_col=time_cols,
        list_col=language_col,
        prefix=prefix,
        features=features,
    )    
    
    df_lan_dedup = df_lan.drop(columns=[language_col]).drop_duplicates()
    
    n_unique_col = [col for col in df_lan_dedup.columns if col.endswith("n_uniq")]
        
    if len(n_unique_col) >= 1:
        # only keep the one with largest n_uniq
        df_lan_dedup = (
            df_lan_dedup.sort_values(n_unique_col, ascending=[False]*len(n_unique_col))
            .drop_duplicates(subset=group_cols, keep="first")
            .sort_values(group_cols)
            .reset_index(drop=True)
        )
        logger.debug("Multiple columns with 'n_uniq' suffix found in derived language features. Only the one with the largest n_uniq value is kept for each student-year. Kept columns: %s",)
    
    assert df_lan_dedup[group_cols].duplicated().sum() == 0, "There are duplicated student-year entries in the derived language features. Please check the derivation logic."
    
    df_new = df.merge(df_lan_dedup, on=group_cols, how='left')
    
    added_cols = set(df_new.columns) - set(input_data.columns)
    if len(added_cols) > 0:
        format_added_cols = pprint.pformat(added_cols, indent=4, compact=True)
        logger.info(
            f"Following columns have been added to the data: \n{format_added_cols}\n"
            f"NOTE: 'Refused/Unknown/Not obtained' categories are treated as non-substantive and are excluded."
        )
    
    log_line_break(logger)
    
    return df_new