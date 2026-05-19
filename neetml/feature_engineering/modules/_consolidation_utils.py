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
from typing import Union, Optional, Sequence, Literal
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

logger = get_logger("feature_engineering")
# logger = logging.getLogger(__name__)  

def _detect_conflicts(
    df: pd.DataFrame,
    group_keys: Union[str, list],
    output_path: Union[str, Path],
    prefixes: list = CATEGORY_PREFIX_MAP.values(),
    stud_id_col: str = STUD_ID_COL,
    sample: bool = True,
    show_progress: bool = True,
    overwrite: bool = False,
    save_conflict_ids: bool = True
):
    conflict_id_path = output_path.parent / "conflict_ids.yaml"
    
    if output_path.exists() and not overwrite:
        logger.info(f"Conflict report already exists at {output_path}. Skipping conflict detection and loading existing report.")
        with open(output_path, "r") as f:
            result = yaml.safe_load(f)
        
        if save_conflict_ids and conflict_id_path.exists():
            logger.info(f"Loading existing conflict IDs from {conflict_id_path}")
            with open(conflict_id_path, "r") as f:
                conflict_ids_dict = yaml.safe_load(f)
            
            return result, conflict_ids_dict
        
        return result
    
    logger.info(f"Detecting conflicts based on group_keys: {group_keys}, and saving report to {output_path} (overwrite={overwrite})")
    logger.info(f"Columns with following prefixes will be considered for conflict detection: {', '.join(prefixes)}")
    
    columns = {} # save cols with conflicts
    unprocessed_cols = []
    conflict_ids_dict = {}
    
    if isinstance(group_keys, str):
        group_keys = [group_keys]

    check_cols = [col for col in df.columns if any(col.startswith(prefix) for prefix in prefixes)]
    
    # iterator = tqdm(df.columns, desc="Detecting conflicts", unit="col") if show_progress else df.columns
    iterator = tqdm(check_cols, desc="Detecting conflicts", unit="col") if show_progress else check_cols

    for col in iterator:
        if show_progress:
            iterator.set_description(f"Checking {col}")
        
        if col in group_keys:
            continue
            
        s = df[group_keys + [col]].dropna(subset=[col], how='all')
        if s.empty:
            continue
        
        if s[col].map(lambda x: isinstance(x, np.ndarray)).any():
            logger.debug(f"{col} is a numpy.ndarray, won't be used for detecting conflicts.")
            unprocessed_cols.append(col)
            continue
        
        nunique_per_id = s.groupby(group_keys)[col].nunique()
            
        conflict_ids = nunique_per_id[nunique_per_id > 1].index

        n_conflict = len(conflict_ids)
        if n_conflict == 0:
            continue
        
        entry = {
            "dtype": str(df[col].dtype),
            "conflict_student_count": int(n_conflict),
            # "aggregation": (
            #     "sum" if pd.api.types.is_numeric_dtype(df[col]) and '%' not in col
            #     else "ignore" if pd.api.types.is_numeric_dtype(df[col]) and '%' in col # percentage columns will be recalculated
            #     else "max" if pd.api.types.is_bool_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col])
            #     else "list"
            # ),
        }

        if sample:
            first_id = conflict_ids[0]
            
            if isinstance(first_id, tuple):
                first_id = list(first_id)
            else:
                first_id = [first_id]
            
            first_values = (
                s.loc[s[group_keys].eq(first_id).all(axis=1), col]
                .drop_duplicates()
                .tolist()
            )
            entry["first_conflict_id"] = ', '.join(map(str, first_id))
            entry["first_conflict_values"] = ', '.join(map(str, first_values))

        columns[col] = entry
        
        if save_conflict_ids:
            prefix_for_col = col.split('_')[0] if '_' in col else 'uncategorized'
            if prefix_for_col not in prefixes:
                continue
            else:
                conflict_ids_dict.setdefault(prefix_for_col, set()).update(
                    conflict_ids.get_level_values(stud_id_col)
                )
                

    # sort columns by column name
    columns = dict(sorted(columns.items(), key=lambda item: item[0]))
    
    # calculate the number of columns with conflicts in each data category
    n_cols_in_category = {f"* n_cols_in_{category.lower()}": sum(1 for col in columns if category in col.lower()) for category in prefixes}
    
    result = {
        "* group keys": ', '.join(group_keys),
        "* n_cols_with_conflict": len(columns),
        **n_cols_in_category,
        "* n_cols_unprocessed": f"{len(unprocessed_cols)}, ({", ".join(unprocessed_cols)})",
        "* n_total_columns": len(df.columns),
        "* n_person_with_conflicts": len(set().union(*conflict_ids_dict.values())) if conflict_ids_dict else "Unknown",
        # "* aggregation_options": ', '.join(map(str, ["ignore", "first", "list", "mean", "sum", "max", "min", "drop"])), # not used
        "columns": columns,
    }

    yml = yaml.dump(result, sort_keys=False, allow_unicode=True)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(yml)
    
    if save_conflict_ids:
        conflict_ids_dict = {
            k: ', '.join(v)
            for k, v in conflict_ids_dict.items()
        }
        
        yaml_for_conflict_ids = yaml.dump(conflict_ids_dict, sort_keys=False, allow_unicode=True)
        with open(conflict_id_path, "w", encoding="utf-8") as f:
            f.write(yaml_for_conflict_ids)
    
    return (result, conflict_ids_dict) if save_conflict_ids else result

def _resolve_census_conflicts(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    dob_col: str = "census_date_of_birth",
    census_age_col: str = "census_age",
    entry_date_col: str = "census_entry_date",
    enrol_status_col: str = "census_enrol_status",
    enrol_priority: dict[str, int] | None = None,
    drop_audit_cols: bool = True,
) -> pd.DataFrame:
    """
    Resolve conflicts in census data by selecting one record per group defined by `group_cols` based on enrolment priority and age consistency.
    
    Rules:
    1. Calculate age at entry based on date of birth and entry date, and compare with census age to get an age error.
    2. Rank records within each group by:
       a. Smallest age error (more consistent with census age is better)
       b. Smallest enrolment status priority (e.g. M > C > S)
       c. Most recent entry date (more recent is better)
    3. Select the top-ranked record for each group as the resolved record.

    Parameters
    ----------
    df:
        Input census-level dataframe.

    group_cols:
        Columns that define one logical census record.
        Usually something like:
            ["stud_id", "academic_year"]
        or:
            ["stud_id", "academic_year", "census_date"]

    enrol_status_col:
        Column containing enrolment status, e.g. C, M, S.
        
    dob_col:
        Column containing date of birth.
    
    entry_date_col:
        Column containing enrolment entry date.
    
    census_age_col:
        Column containing census age.

    enrol_priority:
        Optional priority mapping. Lower number = higher priority.

    keep_conflict_flags:
        Whether to add conflict diagnostic columns.

    drop_helper_cols:
        Whether to drop temporary priority column before returning.

    Returns
    -------
    pd.DataFrame
        One row per group_cols, selected by enrolment priority,
        with optional conflict flags.
    """

    if enrol_priority is None:
        enrol_priority = {
            "M": 1,  # current main, dual registration main school
            "C": 2,  # current single registration
            "S": 3,  # current subsidiary
        }
    
    logger.info(
        "\nResolving census data conflicts. Grouping by %s. Records are ranked by: \n"
        "1) smallest age error between age at entry and census age, \n"
        "2) highest enrolment status priority %s, \n"
        "3) most recent entry date.\n",
        group_cols,
        enrol_priority,
    )
        
    df_new = df.copy()

    df_new[dob_col] = pd.to_datetime(df_new[dob_col], errors="coerce")
    df_new[entry_date_col] = pd.to_datetime(df_new[entry_date_col], errors="coerce")
    df_new["_census_age_num"] = pd.to_numeric(df_new[census_age_col],errors="coerce",)
    df_new["_age_at_entry"] = (df_new[entry_date_col] - df_new[dob_col]).dt.days / 365.25
    df_new["_age_error"] = (df_new["_age_at_entry"] - df_new["_census_age_num"]).abs()
    
    df_new["_enrol_priority"] = (
        df[enrol_status_col]
        .astype("string")
        .str.strip()
        .str.upper()
        .map(enrol_priority)
        .fillna(99)
        .astype(int)
    )
    
    df_new = df_new.sort_values(
        by=[
            *group_cols,
            "_age_error",
            "_enrol_priority",
            entry_date_col,
        ],

        ascending=[
            *([True] * len(group_cols)),
            True, # smaller age error is better
            True, # smaller enrolment priority is better
            False, # more recent entry date is better
        ],
        na_position="last",
    )

    df_resolved = df_new.drop_duplicates(subset=group_cols, keep="first")

    if drop_audit_cols:
        df_resolved = df_resolved.drop(columns=["_census_age_num", "_age_at_entry", "_age_error", "_enrol_priority"], errors="ignore")

    # double-check
    if df_resolved.duplicated(subset=group_cols).any():
        duplicated_groups = df_resolved[df_resolved.duplicated(subset=group_cols, keep=False)][group_cols]
        raise ValueError(f"After resolving census conflicts, there are still duplicated records for the following groups:\n{duplicated_groups}")
    else:
        logger.debug("No duplicate records remain after resolving census conflicts.")
    
    logger.debug(f"Resolved census conflicts, reduced from {len(df)} to {len(df_resolved)} records.")
    
    log_line_break(logger)
    
    return df_resolved

def _resolve_ks_conflicts(
    df: pd.DataFrame,
    # stud_id_col: str = STUD_ID_COL,
    group_cols: list = [STUD_ID_COL],
    dob_col: str = None,
    ks2_year_col: str = None,
    ks4_year_col: str = None,
    fill_cols: Sequence[str] | None = None,
    backfill: bool = True,
    drop_audit_cols: bool = True,
) -> pd.DataFrame:
    """
    Resolve duplicated KS2/KS4 records using DOB-derived expected KS2/KS4 assessment year.

    Strategy
    --------
    1. Calculate expected KS2/KS4 assessment year from date of birth (if dob provided).
    2. Select the most completed KS2/KS4 row as the base row.
    3. If there is a tie, select the row closest to the expected KS2/KS4 year (if dob provided).
    4. Use other duplicate rows only to fill missing values in the base row.
    5. If duplicate rows contain conflicting non-missing values, keep the base row value
       and record conflict diagnostics.
    """

    df_new = df.copy()
    # df_new["_original_order"] = range(len(df_new))
    
    if ks2_year_col is not None and ks4_year_col is not None:
        raise ValueError("Only one of ks2_year_col and ks4_year_col should be provided, but got both.")
    
    if dob_col is not None:
        dob = pd.to_datetime(df_new[dob_col], errors="coerce")
        birth_year = dob.dt.year
        birth_month = dob.dt.month

        # Born Sep-Dec: belongs to cohort starting school the next calendar year group, KS2 assessment is in birth_year + 12.
        # Born Jan-Aug: KS2 assessment is in birth_year + 11.
        df_new["_expected_ks2_year"] = birth_year + birth_month.ge(9).astype("Int64") + 11
        
        # similar for KS4
        df_new["_expected_ks4_year"] = birth_year + birth_month.ge(9).astype("Int64") + 16
    
    if ks2_year_col is not None:
        df_new["_ks_year_numeric"] = pd.to_numeric(df_new[ks2_year_col], errors="coerce")
        df_new["_ks_year_distance"] = (df_new["_ks_year_numeric"] - df_new["_expected_ks2_year"]).abs()
        
    if ks4_year_col is not None:
        df_new["_ks_year_numeric"] = pd.to_numeric(df_new[ks4_year_col], errors="coerce")
        df_new["_ks_year_distance"] = (df_new["_ks_year_numeric"] - df_new["_expected_ks4_year"]).abs()

    if fill_cols is None and backfill:
        fill_cols = df_new.columns
        logger.debug(f"No fill_cols specified for resolving conflicts, all columns will be considered for filling missing values. If you want to specify which columns to use for filling, please provide a list of column names in the fill_cols parameter.")
        logger.info(
            "Data conflict resolver will select most complete as base row per student, then backfill missing "
            "values in that base row from the student's duplicate rows. Since fill_cols=None, "
            "all columns will be backfilled where missing, including possible school/year/id/meta "
            "columns. Pass fill_cols to restrict backfill to selected attainment/background fields."
        )
    else:
        if backfill:
            formatted_fill_cols = pprint.pformat(fill_cols, indent=4, compact=True)
            logger.debug(f"\nUsing specified fill_cols for resolving conflicts: \n{formatted_fill_cols}\n")
            logger.info(
                "Data conflict resolver will select most complete row as base row per student, then backfill missing "
                "values only in the specified fill_cols from duplicate rows.",
            )
        else:
            logger.info(
            "Data conflict resolver will select most complete as base row per student. Backfill is disabled, "
            "so missing values in the selected base row will not be filled from duplicate rows."
        )

    fill_cols = [col for col in fill_cols if col in df_new.columns]

    df_new["_ks_completeness"] = df_new[fill_cols].notna().sum(axis=1)

    # Select base row: closest to expected most complete > KS2/KS4 year
    # then backfill the missing value in base row from later rows within the same group.
    has_year_col = ks2_year_col is not None or ks4_year_col is not None

    sort_cols = group_cols + ["_ks_completeness"]
    ascending = [True] * len(group_cols) + [False]

    if has_year_col:
        sort_cols.append("_ks_year_distance")
        ascending.append(True)

    df_sorted = (
        df_new.sort_values(by=sort_cols, ascending=ascending)
        .copy()
    )

    df_sorted[fill_cols] = (
        df_sorted
        .groupby(group_cols, dropna=False)[fill_cols]
        .bfill()
    )

    df_resolved = (
        df_sorted
        .drop_duplicates(subset=group_cols, keep="first")
        .reset_index(drop=True)
        .copy()
    )
    
    if drop_audit_cols:
        df_resolved = df_resolved.drop(columns=["_expected_ks2_year", "_expected_ks4_year", "_ks_year_numeric", "_ks_year_distance", "_ks_completeness"], errors="ignore")

    # double-check
    if df_resolved.duplicated(subset=group_cols).any():
        duplicated_groups = df_resolved[df_resolved.duplicated(subset=group_cols, keep=False)][group_cols]
        raise ValueError(f"After resolving KS conflicts, there are still duplicated records for the following groups:\n{duplicated_groups}")
    else:
        logger.debug("No duplicate records remain after resolving KS conflicts.")
    
    logger.debug(f"Resolved attainment data conflicts, reduced from {len(df)} to {len(df_resolved)} records.")
    
    log_line_break(logger)
    
    return df_resolved

def _resolve_susp_conflicts(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    date_col: str = "suspPermExcl_exclusion_start_date",
    prefix: str = "suspPermExcl",
) -> pd.DataFrame:
    """
    Resolve susp/exclusion records by keeping the latest event per group,
    and adding the number of events within each group.

    Parameters
    ----------
    df:
        Input event-level dataframe.

    group_cols:
        Columns defining one output row.
        Example: ["stud_id", "_year_group"]

    date_col:
        Event date column used to select the latest event.

    prefix:
        Prefix for generated feature columns.

    Returns
    -------
    pd.DataFrame
        One row per group, keeping the latest event row and adding event count.
    """

    df_new = df.copy()
    group_cols = list(group_cols)

    missing_cols = set(group_cols + [date_col]) - set(df_new.columns)
    if missing_cols:
        raise KeyError(f"Missing required columns: {sorted(missing_cols)}")
    
    df_new[date_col] = pd.to_datetime(df_new[date_col], errors="coerce")

    event_count = (
        df_new.groupby(group_cols, dropna=False)
        .size()
        .rename(f"{prefix}_event_count")
        .reset_index()
    )

    latest = (
        df_new.sort_values(
            by=group_cols + [date_col],
            ascending=[True] * len(group_cols) + [False],
            # na_position="last",
        )
        .drop_duplicates(subset=group_cols, keep="first")
        .copy()
    )

    df_resolved = latest.merge(
        event_count,
        on=group_cols,
        how="left",
    )
    
    # double-check
    if df_resolved.duplicated(subset=group_cols).any():
        duplicated_groups = df_resolved[df_resolved.duplicated(subset=group_cols, keep=False)][group_cols]
        raise ValueError(f"After resolving susp/exclu conflicts, there are still duplicated records for the following groups:\n{duplicated_groups}")
    else:
        logger.debug("No duplicate records remain after resolving susp/exclu conflicts.")
    
    logger.info(f"Resolved susp/exclu data conflicts by keeping the latest event per group and adding event count. Grouped by {group_cols}, sorted by {date_col} to select latest event. '{prefix}_event_count' column added to indicate number of events in each group.")
    
    logger.debug(f"Resolved susp/exclu data conflicts, reduced from {len(df)} to {len(df_resolved)} records.")
    
    log_line_break(logger)

    return df_resolved.reset_index(drop=True)

def _resolve_att_conflicts(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    prefix: str = "attendance",
    possible_sessions_col: str = "attendance_possible_sessions",
    keep: Literal["last", "first"] = "last",
) -> pd.DataFrame:
    """
    Resolve duplicated attendance records by aggregating counts and recalculating percentages.

    Strategy
    --------
    1. Sum all count/session columns within each group.
    2. Recalculate percentage columns from their corresponding count columns.
    3. For non-aggregated identity/context columns, keep the first/last row if requested.

    Parameters
    ----------
    df:
        Input attendance dataframe.

    group_cols:
        Columns defining output grain, e.g. ["stud_id", "_year_group"].

    prefix:
        Attendance column prefix.

    possible_sessions_col:
        Denominator column used to recalculate percentages.

    keep:
        Whether to keep non-count/non-percentage columns from the first/last row.

    Returns
    -------
    pd.DataFrame
        One row per group.
    """

    df_new = df.copy()
    group_cols = list(group_cols)

    missing = set(group_cols) - set(df_new.columns)
    if missing:
        raise KeyError(f"Missing group columns: {sorted(missing)}")

    if possible_sessions_col not in df_new.columns:
        raise KeyError(f"Missing possible sessions column: {possible_sessions_col}")
    
    
    attendance_cols = [col for col in df_new.columns if col.startswith(prefix)]

    # find count cols
    count_cols = [col for col in attendance_cols if col.endswith("_count")]
    
    # find pct cols
    pct_cols = [col for col in attendance_cols if col.endswith("_%")]
    
    # Include possible sessions in sum columns
    # sum_cols = list(dict.fromkeys(count_cols + [possible_sessions_col]))
    sum_cols = list(set(count_cols + [possible_sessions_col]))
    
    other_cols = list(set(df_new.columns) - set(sum_cols) - set(pct_cols))
    
    df_others_sort = (
        df_new.sort_values(
            by=group_cols,
            ascending=[True] * len(group_cols),
            na_position="last",
        )
        .drop_duplicates(subset=group_cols, keep=keep)
        [other_cols]
        .copy()
    )
    
    fmt_pct_cols = pprint.pformat(', '.join(pct_cols), indent=4, compact=True)
    logger.info(
        f"\nFollowing pct columns will be recalculated:\n{fmt_pct_cols}\n"
        f"For other columns, only {keep} one will be kept."
    )

    for col in sum_cols + pct_cols:
        if col in df_new.columns:
            df_new[col] = pd.to_numeric(df_new[col], errors="coerce")

    # Sum count/session columns
    agg = (
        df_new.groupby(group_cols, dropna=False)[sum_cols]
        .sum(min_count=0)
        .reset_index()
    )

    # Recalculate percentage columns from corresponding counts
    # Example:
    # attendance_absence_% -> attendance_absence_count / attendance_possible_sessions
    denom = agg[possible_sessions_col]

    for pct_col in pct_cols:
        base = pct_col[:-2]  # remove "_%"
        count_col = f"{base}_count"

        if count_col in agg.columns:
            agg[pct_col] = (
                agg[count_col]
                .div(denom)
                .mul(100)
                .where(denom.ne(0))
            )
        
            logger.debug(f"Recalculated percentage column '{pct_col}' from count column '{count_col}' and denominator '{possible_sessions_col}'.")
        
        else:
            raise ValueError(f"Cannot find count col '{count_col}' for pct col '{pct_col}'.")
        
    df_resolved = df_others_sort.merge(
        agg,
        on=group_cols,
        how="left",
    )
    df_resolved = df_resolved[df.columns]
    
    # double-check
    if df_resolved.duplicated(subset=group_cols).any():
        duplicated_groups = df_resolved[df_resolved.duplicated(subset=group_cols, keep=False)][group_cols]
        raise ValueError(f"After resolving attendance conflicts, there are still duplicated records for the following groups:\n{duplicated_groups}")
    else:
        logger.debug("No duplicate records remain after resolving attendance conflicts.")
    
    logger.debug(f"Resolved attendance data conflicts, reduced from {len(df)} to {len(df_resolved)} records.")
    
    log_line_break(logger)

    return df_resolved.reset_index(drop=True)
