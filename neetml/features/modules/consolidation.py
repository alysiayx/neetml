from functools import reduce
import logging
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
from typing import Union, Optional
from tqdm.auto import tqdm
# from rich.progress import Progress
import pprint

from ...utils.misc import (
    styled_print,
    load_dataframe
)

from ...utils.constants import (
    ExtRefs,
    CSP_CONFIGS,
    EXT_COL_PREFIX,
    DATA_PATHS,
    MergeMetadata,
    STUD_ID_COL,
    DATA_CATEGORIES,
    CATEGORY_PREFIX_MAP
) 

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from ._consolidation_utils import (
    _detect_conflicts,
    _resolve_census_conflicts,
    _resolve_ks_conflicts,
    _resolve_susp_conflicts,
    _resolve_att_conflicts
)

logger = get_logger("feature_engineering")
# logger = logging.getLogger(__name__)  

def _prepare_data(
    df: pd.DataFrame,
    data_type: str,
    prefixes: str | list,
    group_keys: list[str],
    stud_id_col: str,
    conflict_ids: dict[str, set] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """
    Prepare conflict and non-conflict records for one data type.

    Returns
    -------
    df_conflict:
        Rows to be processed by the conflict resolver.

    df_non_conflict:
        Rows that do not need conflict resolution.

    data_cols:
        Columns belonging to this data type.
    """

    if isinstance(prefixes, str):
        prefixes = [prefixes]

    data_cols = [col for col in df.columns if any(col.startswith(prefix) for prefix in prefixes)]

    if not data_cols:
        return pd.DataFrame(), pd.DataFrame(), []

    keep_cols = list(dict.fromkeys(group_keys + data_cols))

    df_data = (
        df[keep_cols]
        .drop_duplicates()
        .dropna(subset=data_cols, how="all")
    )

    if df_data.empty:
        return df_data, pd.DataFrame(), data_cols

    if conflict_ids is not None:
        ids_for_type = set(conflict_ids.get(data_type, set())) if conflict_ids else set()

        mask_conflict = df_data[stud_id_col].isin(ids_for_type)

        df_conflict = df_data.loc[mask_conflict].copy()
        df_non_conflict = df_data.loc[~mask_conflict].copy()

        logger.info("Number of people with conflicts in %s data: %s", data_type, df_conflict[stud_id_col].nunique())
    else:
        logger.info(
            "All records in %s data will be processed for conflict resolution "
            "because conflict_ids is None.",
            data_type,
        )

        df_conflict = df_data.copy()
        df_non_conflict = pd.DataFrame(columns=df_data.columns)

    return df_conflict, df_non_conflict, data_cols

def resolve_conflicts(
    input_data: Union[str, Path, pd.DataFrame],
    conflict_output_path: Union[str, Path],
    group_keys: Union[str, list],
    prefix_map: dict,
    stud_id_col: str = STUD_ID_COL,
    use_conflict_ids: bool = True,
    overwrite: bool = False,
    **kwargs
):    
    
    if use_conflict_ids:
        save_conflict_ids = True
    else:
        save_conflict_ids = False
    
    df = input_data.copy()
    
    DEFAULT_CATEGORY_NAME = CATEGORY_PREFIX_MAP.keys()
    
    formatted_prefix_map = "\n".join(
        f"  - {category}: {prefix}"
        for category, prefix in prefix_map.items()
    )
    
    logger.debug(
        f"\nPrefix map provided. Format: category -> prefix: \n{formatted_prefix_map}."
        f"\nThe category names defined in the prefix_map must be any of the following: "
        f"{list(DEFAULT_CATEGORY_NAME)}."
    )
    
    valid_cat_prefix_map = {cat: prefix_map.get(cat, []) for cat in DEFAULT_CATEGORY_NAME}
    
    # first detect conflicts and save the results in a yaml file
    conflict_results = _detect_conflicts(
        df, 
        group_keys=group_keys, 
        prefixes=valid_cat_prefix_map.values(), 
        stud_id_col=stud_id_col,
        output_path=conflict_output_path, 
        save_conflict_ids=save_conflict_ids,
        overwrite=overwrite,
    )
        
    if save_conflict_ids:
        conflict_ids = conflict_results[1]
        conflict_ids = {k: [str(x).strip() for x in v.split(',')] for k, v in conflict_ids.items()}
        logger.info(f"Following data categories have conflicts and will be processed by the conflict resolver: {list(conflict_ids.keys())}.")
    else:
        conflict_ids = None
    
    if not valid_cat_prefix_map:
        raise ValueError(f"The category names defined in the prefix_map must be any of the following: {DEFAULT_CATEGORY_NAME}, but got {prefix_map.keys()}. Please update the prefix_map to use valid category names.")
    
    log_line_break(logger)
    
    # --------------------------------
    # resolve conflicts in census data
    # --------------------------------
    
    kwargs_pre_data = {
        "group_keys": group_keys,
        "stud_id_col": stud_id_col,
        "conflict_ids": conflict_ids,
    }
    
    df_census_conflit, df_census_non_conflit, _ = _prepare_data(
        df,
        data_type=prefix_map.get("census", ""),
        prefixes=prefix_map.get("census", ""),
        **kwargs_pre_data
    )
        
    census_resolve_kwargs = kwargs.get("census", {})
    
    df_census_resloved = _resolve_census_conflicts(
        df_census_conflit,
        group_cols=group_keys,
        **census_resolve_kwargs,
    )
    
    df_census_new = pd.concat([df_census_resloved, df_census_non_conflit], ignore_index=True)
    
    # --------------------------------
    # resolve conflicts in ks2 data
    # --------------------------------
    
    external_prefix = prefix_map.get("external", "")
    ext_ks2_prefix = f"{str(external_prefix).rstrip('_')}_ks2"
    ks2_prefix = prefix_map.get("ks2", "")
    
    df_ks2_conflit, df_ks2_non_conflit, _ = _prepare_data(
        df,
        data_type=ks2_prefix,
        prefixes=[ks2_prefix, ext_ks2_prefix],
        # **(kwargs_pre_data | {"group_keys": [stud_id_col]}),
        **kwargs_pre_data,
    )
    
    # add dob for each person
    dob_col = "census_date_of_birth"
    dob = df[[stud_id_col, dob_col]].drop_duplicates().dropna(subset=[dob_col])
    df_ks2_conflit = df_ks2_conflit.merge(dob, on=stud_id_col, how='left').drop_duplicates()
    
    ks2_include_patterns = (
        "lev", "mrk", "mark", "score", "outcome", "exp", "high", "depth",
        "wts", "bexp", "ad", "elig", "val", "prog", "pred", "ps",
        "ks1", "aps", "eal", "sen", "fsm", "mobile", "cla", "amdpupil", "speccon",
    )

    ks2_exclude_patterns = (
        "urn", "la", "estab", "laestab", "acadyr", "yeargrp", "examyear",
        "cand", "matching", "version", "school_type",
        "schres", "lares", "natres", "nftype", "toe_code",
        "mmsch", "msch", "open_ac", "endks", "npdden",
    )
    
    fill_cols = [
        col for col in df.columns
        if col.startswith(ks2_prefix)
        and any(p in col.lower() for p in ks2_include_patterns)
        and not any(p in col.lower() for p in ks2_exclude_patterns)
    ]
    
    ks2_resolve_kwargs = kwargs.get("ks2", {})
    
    df_ks2_resolved = _resolve_ks_conflicts(
        df_ks2_conflit,
        fill_cols=fill_cols,
        dob_col="census_date_of_birth",
        ks2_year_col="ks2_examyear_re",
        group_cols=group_keys,
        **ks2_resolve_kwargs
    )
    
    df_ks2_resolved.drop(columns=dob_col, inplace=True)
    
    df_ks2_new = pd.concat([df_ks2_resolved, df_ks2_non_conflit], ignore_index=True)
    
    # --------------------------------
    # resolve conflicts in ks4 data
    # --------------------------------
    
    ext_ks4_prefix = f"{str(external_prefix).rstrip('_')}_ks4"
    ks4_prefix = prefix_map.get("ks4", "")
    
    df_ks4_conflit, df_ks4_non_conflit, _ = _prepare_data(
        df,
        data_type=ks4_prefix,
        prefixes=[ks4_prefix, ext_ks4_prefix],
        **kwargs_pre_data,
    )
    
    ks4_include_patterns = (
        "entry", "entries", "entered", "examcat", "entbasics", "pass", 
        "level", "lev", "gcse", "ebac", "basics", "eng", "math", "mat", 
        "sci", "hum", "lan", "mfl",  "pts", "point", "score", "scr",
        "grade", "_g", "att8", "p8", "vap", "va", "pred", "resid",
        "aps", "band", "prior", "ap", "fsm", "eal", "flang", "female", 
        "gender", "mobile", "amd", "idaci", "ks2",
    )
    
    ks4_exclude_patterns = (
        "estab", "laestab", "urn", "cand", "matching", "acadyr", "yeargrp", 
        "version", "cohort", "school_type", "open_ac", "toe_code", "nftype",
        "new_type", "newer_type", "mmsch", "msch", "schres", "lares", "natres",
        "natmtdres", "schnor", "lanor", "natnor", "npdden", "npdnum",
        "la_9code", "norflage",
    )
    
    fill_cols = [
        col for col in df.columns
        if col.startswith(ks4_prefix)
        and any(p in col.lower() for p in ks4_include_patterns)
        and not any(p in col.lower() for p in ks4_exclude_patterns)
    ]
    
    ks4_resolve_kwargs = kwargs.get("ks4", {})
    
    df_ks4_resolved = _resolve_ks_conflicts(
        df_ks4_conflit,
        fill_cols=fill_cols,
        group_cols=group_keys,
        **ks4_resolve_kwargs
    )
    
    df_ks4_new = pd.concat([df_ks4_resolved, df_ks4_non_conflit], ignore_index=True)
    
    # --------------------------------
    # resolve conflicts in susp/exclu data
    # --------------------------------
    
    ext_susp_prefix = f"{str(external_prefix).rstrip('_')}_susp"
    susp_prefix = prefix_map.get("susp", "")
    
    df_susp_conflit, df_susp_non_conflit, _ = _prepare_data(
        df,
        data_type=susp_prefix,
        prefixes=[susp_prefix, ext_susp_prefix],
        **kwargs_pre_data,
    )
    
    susp_resolve_kwargs = kwargs.get("susp", {})
    derived_prefix = prefix_map.get("derived", "")
    der_susp_prefix = f"{str(derived_prefix).rstrip('_')}_susp"
    
    df_susp_resolved = _resolve_susp_conflicts(
        df_susp_conflit,
        group_cols=group_keys,
        prefix=der_susp_prefix,
        **susp_resolve_kwargs
    )
    
    df_susp_new = pd.concat([df_susp_resolved, df_susp_non_conflit], ignore_index=True)
    
    # --------------------------------
    # resolve conflicts in attendance data
    # --------------------------------
    
    att_resolve_kwargs = kwargs.get("att", {})
    ext_att_prefix = f"{str(external_prefix).rstrip('_')}_att"
    att_prefix = prefix_map.get("att", "")
    
    df_att_conflit, df_att_non_conflit, _ = _prepare_data(
        df,
        data_type=att_prefix,
        prefixes=[att_prefix, ext_att_prefix],
        **kwargs_pre_data,
    )
    
    df_att_resolved = _resolve_att_conflicts(
        df_att_conflit,
        prefix=att_prefix,
        group_cols=group_keys,
        **att_resolve_kwargs
    )
    
    df_att_new = pd.concat([df_att_resolved, df_att_non_conflit], ignore_index=True)
    
    # --------------------------------
    # update data
    # --------------------------------
    
    update_cols = list(set(df_census_new.columns) | set(df_att_new.columns) | set(df_ks2_new.columns) | set(df_ks4_new.columns) | set(df_susp_new.columns))
    update_cols = [col for col in update_cols if col not in group_keys]
    new_cols = [col for col in update_cols if col not in df.columns]
    
    df_other = df.drop(columns=[col for col in update_cols if col in df.columns]).copy()
   
    array_cols = [
        col for col in df_other.columns
        if df_other[col].map(lambda x: isinstance(x, np.ndarray)).any()
    ]

    for col in array_cols:
        df_other[col] = df_other[col].map(
            lambda x: tuple(x.tolist()) if isinstance(x, np.ndarray) else x
        )

    df_other = df_other.dropna(axis=1, how='all').drop_duplicates()
    
    # check if there has any conflicts in df_other
    conflict_mask = (
        df_other.groupby(group_keys, dropna=False)
        .nunique(dropna=True)
        .gt(1)
        .drop(columns=group_keys, errors="ignore")
    )

    conflict_groups = conflict_mask[conflict_mask.any(axis=1)]

    if not conflict_groups.empty:
        keys = conflict_groups.head(2).index.to_frame(index=False)

        examples = (
            df_other.merge(keys, on=group_keys, how="inner")
            .groupby(group_keys, dropna=False)
            .agg(lambda s: list(pd.unique(s.dropna())))
        )

        examples = examples.loc[:, examples.map(len).gt(1).any()]

        raise ValueError(
            f"There are {len(conflict_groups)} duplicated groups with conflicting records.\n"
            f"Showing first 2 conflict groups and their conflicting values:\n{examples}"
        )
    
    df_final = reduce(
        lambda left, right: left.merge(right, on=group_keys, how='left'),
        [df_other, df_census_new, df_att_new, df_ks2_new, df_ks4_new, df_susp_new]
    )
    
    df_final = df_final[list(df.columns) + new_cols]
    
    # # double-check
    # if df_final.duplicated(subset=group_keys).any():
    #     duplicated_groups = df_final[df_final.duplicated(subset=group_keys, keep=False)][group_keys]
    #     raise ValueError(f"After resolving conflicts, there are still {duplicated_groups.shape[0]} duplicated records for the following groups:\n{duplicated_groups}")
    # else:
    #     logger.debug("No duplicate records remain after resolving attendance conflicts.")
    
    
    conflict_mask = (
        df_final.groupby(group_keys, dropna=False)
        .nunique(dropna=True)
        .gt(1)
        .drop(columns=group_keys, errors="ignore")
    )

    conflict_groups = conflict_mask[conflict_mask.any(axis=1)]

    if not conflict_groups.empty:
        keys = conflict_groups.head(2).index.to_frame(index=False)

        examples = (
            df_final.merge(keys, on=group_keys, how="inner")
            .groupby(group_keys, dropna=False)
            .agg(lambda s: list(pd.unique(s.dropna())))
        )

        examples = examples.loc[:, examples.map(len).gt(1).any()]

        raise ValueError(
            f"There are {len(conflict_groups)} duplicated groups with conflicting records in the final data.\n"
            f"Showing first 2 conflict groups and their conflicting values:\n{examples}"
        )
    
    logger.info(f"Finished resolving conflicts and updating data. Reduce shape of input data from {df.shape} to {df_final.shape}.")
    
    # # double-check conflicts
    # _ = _detect_conflicts(
    #     df_final, 
    #     group_keys=group_keys, 
    #     prefixes=valid_cat_prefix_map.values(), 
    #     stud_id_col=stud_id_col,
    #     output_path=conflict_output_path.parent / f"{conflict_output_path.stem}_post_resolve.yaml", 
    #     save_conflict_ids=False,
    #     overwrite=True,
    # )
    
    return df_final