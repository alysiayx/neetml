from datetime import datetime
from math import log
from pickletools import int4
import pandas as pd
import janitor
import os
import requests
from bs4 import BeautifulSoup
import zipfile
import io
from pathlib import Path
import cgi
from typing import Literal, Union

from ..utils.misc import (
    styled_print,
    set_default_path,
    load_dataframe,
    resolve_dataframe
)

from ..utils.constants import (
    DER_COL_PREFIX,
    EXT_COL_PREFIX,
    ExtRefs,
    CSP_CONFIGS,
    DATA_PATHS,
    STUD_ID_COL,
    MergeMetadata,
    DATA_CATEGORIES,
    CATEGORY_PREFIX_MAP
) 

from ..utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from .modules.linking import (
    add_iod as _add_iod,
    fetch_school_perf_data as _fetch_school_perf_data,
    build_school_perf_data as _build_school_perf_data,
    link_school_perf_data as _link_school_perf_data,
)

from .modules.consolidation import resolve_conflicts as _resolve_conflicts

from .modules.derivation import (
    derive_ethnic_features,
    derive_gender_features,
    derive_school_features,
    derive_language_features
)


logger = get_logger("feature_engineering")


class FeatEngineer:
    def __init__(
        self,
        input_data_path: Union[str, Path] = None,
        save_data_name: str = "data.parquet",
        ext_data_dir: Union[str, Path] = None,
        proc_data_dir: Union[str, Path] = None,
        ext_link_dir: str = "3_ext_linked",
        derive_dir: str = "4_derived",
        agg_dir: str = "5_aggregated",
        prefix: dict = {
            "derived": DER_COL_PREFIX,
            "external": EXT_COL_PREFIX,
        },
        overwrite: bool = False,
    ):
        """
        Initializes the FeatEngineer class with specified directories for input, external data, and processed data.
        
        Parameters
        ----------
        - ext_data_dir: Directory for external data sources (e.g., IoD, IMD datasets).
        - proc_data_dir: Directory for processed data outputs (e.g., aggregated datasets, feature-engineered datasets).
        - ext_link_dir: Subdirectory name for externally linked data within the processed data directory.
        - derive_dir: Subdirectory name for derived data within the processed data directory.
        - agg_dir: Subdirectory name for aggregated data within the processed data directory.
        - overwrite: Whether to overwrite existing files when saving outputs.
        """
        
        paths = {
            "ext_data_dir": ext_data_dir,
            "proc_data_dir": proc_data_dir,
        }
        
        for key, user_path in paths.items():
            default_value = DATA_PATHS[key.upper()]
            setattr(self, key, set_default_path(user_path, default_value))
        
        subfolders = {
            "agg_data_dir": agg_dir,
            "link_data_dir": ext_link_dir,
            "derive_data_dir": derive_dir,
        }       
        
        for key, folder in subfolders.items():
            default_value = DATA_PATHS[key.upper()]
            setattr(self, key, set_default_path(self.proc_data_dir / folder, default_value))
        
        for path in subfolders.values():
            (self.proc_data_dir / path).mkdir(parents=True, exist_ok=True)

        self.overwrite = overwrite
        self.prefix = prefix
        self.input_data_path = input_data_path
        self.save_data_name = save_data_name
        logger.info(f"The default name for saving output data is set to {self.save_data_name}. You can change this using the 'set_save_data_name' method or by providing a different name when calling methods that save output data.")
    
    #############################################
    # Utility Functions
    #############################################
        
    def set_input_data_path(self, path: Union[str, Path]):
        path = Path(path)
        self.input_data_path = path
        logger.info(f"Input data path set to '{self.input_data_path}'")
    
    def set_save_data_name(self, name: str):
        self.save_data_name = name
        logger.info(f"Save data name set to '{self.save_data_name}'")
    
    def get_data_path(
        self, 
        keys: Union[
            Literal["input", "external", "processed", "derived", "aggregated", "all"],
            list
        ],
        return_as_dict: bool = False,
    ) -> Union[Path, dict, pd.DataFrame]:
        """
        Retrieve the appropriate data path based on the specified data type.

        Parameters
        ----------
        keys : str or list of str
            The type(s) of data path to retrieve. Options are:
            - "input": Input data path.
            - "external": External data path.
            - "processed": Processed data path.
            - "derived": Derived data path.
            - "aggregation": Aggregated data path.
            - "all": Return all paths as a dictionary.

        return_as_dict : bool, optional
            If True, return as a dictionary. If False, return as a pandas DataFrame.
            - "input": Input data path.
            - "external": External data path.
            - "processed": Processed data path.
            - "derived": Derived data path.
            - "aggregation": Aggregated data path.
            - "all": Return all paths as a dictionary.

        return_as_dict : bool, optional
            If True, return as a dictionary. If False, return as a pandas DataFrame.
            Default is False.

        Returns
        -------
        Path | dict | pd.DataFrame
            - If a single key is provided, returns the corresponding Path.
            - If multiple keys are provided or key="all":
                - Returns a dictionary if `return_as_dict=True`.
                - Returns a pandas DataFrame if `return_as_dict=False`.
        
        Raises
        ------
        ValueError
            If the specified data type is invalid.
        """
        
        # Define mapping with inline description
        paths = {
            "input": (self.input_data_path, "Path for input data"),
            "external": (self.ext_data_dir, "Folder to store external data sources (e.g., IoD, IMD datasets)"),
            "processed": (self.proc_data_dir, "Folder to store processed data outputs (e.g., aggregated datasets, feature-engineered datasets)"),
            "derived": (self.derive_data_dir, "Folder to store data with derived features"),
            "aggregated": (self.agg_data_dir, "Folder to store aggregated data"),
        }

        # Handle "all" option
        if keys == "all":
            selected_keys = list(paths.keys())
        else:
            if isinstance(keys, str):
                keys = [keys]
            selected_keys = keys

            invalid_keys = [k for k in selected_keys if k not in paths]
            if invalid_keys:
                raise ValueError(
                    f"Invalid key(s): {invalid_keys}. "
                    f"Valid options are: {list(paths.keys()) + ['all']}"
                )

        # Construct return structures
        selected_paths = {k: paths[k] for k in selected_keys}

        # Return as dict with embedded descriptions
        if return_as_dict:
            return {
                k: {"path": v[0], "description": v[1]}
                for k, v in selected_paths.items()
            }

        # Return as DataFrame (more readable in notebooks)
        else:
            df = pd.DataFrame(
                [
                    {"Type": k, "Path": v[0], "Description": v[1]}
                    for k, v in selected_paths.items()
                ]
            )
            return df

    #############################################
    # Append School Performance Features
    ##############################################
    
    def download_school_data(
        self,
        la_code: int = 380,
        academic_start_year: int = 2016,
        academic_end_year: int | None = None,
        out_root=None,
        file_format: str = "xlsx",
    ):
        log_with_border(logger, "Downloading School Performance and/or Information Data")
        
        fetch_kwargs = {
            "la_code": la_code,
             "academic_start_year": academic_start_year,
             "academic_end_year": academic_end_year,
             "out_root": out_root,
             "file_format": file_format,
        }
        
        if fetch_kwargs['out_root'] is None:
            fetch_kwargs['out_root'] = self.ext_data_dir
        
        _fetch_school_perf_data(**(fetch_kwargs or {}))
        
        styled_print("School performance data downloaded.", colour='magenta')
    
    def build_school_perf_data(
        self,
        school_perf_dir: Union[str, Path] = None,
        source_mapping: dict = ExtRefs.SCHOOL_SRC_MAPPING,
        join_keys: list = ExtRefs.SCHOOL_JOIN_KEYS,
        save_name: str = ExtRefs.SCHOOL_SAVE_NAME,
    ) -> pd.DataFrame:
        log_with_border(logger, "Creating School Performance and/or Information Data")
        
        build_kwargs = {
            "school_perf_dir": school_perf_dir,
            "source_mapping": source_mapping,
            "join_keys": join_keys,
            "save_name": save_name,
        }
        
        if build_kwargs['school_perf_dir'] is None:
            build_kwargs['school_perf_dir'] = self.ext_data_dir / CSP_CONFIGS["FOLDER_NAME"]
        
        df = _build_school_perf_data(
            **(build_kwargs or {})
        )
        
        styled_print("School performance data created and saved to external linking directory.", colour='magenta')
        
        return df
    
    def link_school_perf_data(
        self,
        input_data: pd.DataFrame = None,
        input_path: Union[str, Path] = None,
        output_dir: Union[str, Path] = None,
        output_name: str = "linked_data_with_school_perf.parquet",
        school_data_path: Union[str, Path] = None,
        school_data: pd.DataFrame = None,
        school_ref: Literal["att", "susp", "ks2", "ks4", "all"] = "all",
        ref_map: dict | None = None,
        join_keys: list[str] | None = None,
        base_join_keys: list[str] = ExtRefs.SCHOOL_JOIN_KEYS,
        input_year_col: str = MergeMetadata.ACAD_YEAR,
        school_year_col: str = ExtRefs.SCHOOL_YEAR_COL,
        lag_years: int = None,
        save_name: str = ExtRefs.SCHOOL_SAVE_NAME,
        prefix: str = None,
        add_lag_suffix: bool = True,
        overwrite=None,
    ) -> pd.DataFrame:
        """
        Link school performance data to student records based on specified reference types and join keys.
        
        Parameters
        ----------
        - input_data: DataFrame containing student records to which school performance data will be linked.
        - input_path: Path to the input data file (if input_data is not provided).
        - school_data_path: Path to the school performance data file (if school_data is not provided).
        - school_data: DataFrame containing school performance data to be linked (if school_data_path is not provided).
        - school_ref: Reference type(s) to use for linking school performance data. Options are:
          - "att": use attendance school identifiers.
          - "susp": use suspension school identifiers.
          - "ks2": use KS2 school identifiers.
          - "ks4": use KS4 school identifiers.
          - "all": use all available school identifiers.
        - ref_map: Optional dictionary mapping reference types to their corresponding join key prefixes and join keys. 
                    If not provided, a default mapping will be used.
        - join_keys: List of join keys to use for linking. If not provided, default join keys from ExtRefs.SCHOOL_JOIN_KEYS will be used.
        - base_join_keys: List of base join keys to use for linking if join_keys is not provided. Default is ExtRefs.SCHOOL_JOIN_KEYS.
        - input_year_col: Column name in the input data that contains the academic year information.
        - school_year_col: Column name in the school performance data that contains the academic year information.
        - lag_years: Number of years to lag the school performance data to ensure only past performance data is linked to each student record.
        - save_name: Name of the file to save the linked data to within the external linking directory.
        - prefix: Prefix to add to the linked school performance features in the output DataFrame.
        - add_lag_suffix: Whether to add a suffix indicating the lag to the linked school performance feature names.
        
        """
        
        log_with_border(logger, "Linking School Performance Data")
        
        if overwrite is None:
            overwrite = self.overwrite
        
        prefix = prefix or self.prefix["external"]
        
        output_dir = set_default_path(output_dir, self.link_data_dir)
        output_path = output_dir / output_name
        
        def _build_join_keys(prefix: str, base_keys: list[str]) -> list[str]:
            return [f"{prefix}_{k}" for k in base_keys]
       
        if output_path.exists() and not overwrite:
            logger.info(f"Linked school performance data already exists at {output_path}. Loading this data.")
            df_new = load_dataframe(output_path)
            logger.info(f"Linked school performance data loaded from {output_path}.")
            return df_new

        df_input = resolve_dataframe(
            df=input_data,
            path=input_path,
            default_path=self.input_data_path,
            name="input data",
            logger=logger
        )
        
        df_school = resolve_dataframe(
            df=school_data,
            path=school_data_path,
            default_path=self.ext_data_dir / CSP_CONFIGS["FOLDER_NAME"] / save_name,
            name="school performance data",
            logger=logger
        )
        
        # Extract academic end year from input_year_col and school_year_col, assuming they are in format "YYYY-YYYY" or "YYYY"
        YEAR_COL = '_year'
        df_input[YEAR_COL] = pd.to_numeric(
            df_input[input_year_col].astype("string").str.strip().str[-4:],
            errors="coerce",
        ).astype("Int64")
        
        df_school[YEAR_COL] = pd.to_numeric(
            df_school[school_year_col].astype("string").str.strip().str[-4:],
            errors="coerce",
        ).astype("Int64")
        
        logger.warning('Assuming academic year columns in input and school data are in format "YYYY-YYYY", "YYYY/YYYY" or "YYYY" and extracting the end year for linking. Please verify that this is correct for your data. If not, please provide the correct year column names or formats.')
        
        # assume basic join-key names follow the standardised `name` defined in `SCHOOL_BASIC_SCHEMA`
        base_join_keys = [
            ExtRefs.SCHOOL_BASIC_SCHEMA.get(k, {}).get("name", k)
            for k in base_join_keys
        ]
        join_keys = base_join_keys if join_keys is None else join_keys
        
        DEFAULT_SCHOOL_REF_MAP = {
            "att": {"prefix": "attendance", "join_keys": _build_join_keys("attendance", join_keys) + [YEAR_COL], "lag": 1 if lag_years is None else lag_years},
            "susp": {"prefix": "suspPermExcl", "join_keys": _build_join_keys("suspPermExcl", join_keys) + [YEAR_COL], "lag": 1 if lag_years is None else lag_years},
            "ks2": {"prefix": "ks2", "join_keys": _build_join_keys("ks2", join_keys) + [YEAR_COL], "lag": 0 if lag_years is None else lag_years},
            "ks4": {"prefix": "ks4", "join_keys": _build_join_keys("ks4", join_keys) + [YEAR_COL], "lag": 1 if lag_years is None else lag_years},
        }
         
        ref_map = ref_map or DEFAULT_SCHOOL_REF_MAP
        df_new = df_input.copy(deep=True) # initialize df_new with input data, then update with linked data for each reference type in the loop
        
        school_ref = [school_ref] if isinstance(school_ref, str) else school_ref
        
        if 'all' in school_ref:
            school_ref = list(ref_map.keys())

        for ref in [school_ref] if isinstance(school_ref, str) else school_ref:
            if ref not in ref_map:
                logger.warning(f"Reference '{ref}' not found in reference map. Skipping this reference.")
                continue
            
            logger.info(
                f"Linking school performance data using reference '{ref}' with prefix '{ref_map[ref]['prefix']}' "
                f"and join keys ({ref_map[ref]['join_keys']}), ({base_join_keys + [YEAR_COL]}) from input and school data respectively, "
                f"and year with lag of {ref_map[ref]['lag']} year(s)."
            )
            
            lag_suffix = f"_lag{ref_map[ref]['lag']}" if add_lag_suffix else ""
            
            df_school_ = df_school.copy(deep=True)
            df_school_[YEAR_COL] = df_school_[YEAR_COL] + ref_map[ref]['lag'] # shift school performance data forward by lag years to ensure only past performance data is linked to each student record based on the academic year

            dup_mask = df_school_.duplicated(subset=base_join_keys + [YEAR_COL], keep=False)
            if dup_mask.any():
                dup_rows = df_school_.loc[dup_mask, base_join_keys + [YEAR_COL]]
                raise ValueError(
                    f"School data is not unique on join keys for ref '{ref}'. "
                    f"Found {dup_rows.shape[0]} duplicate rows."
                )
            
            link_kwargs = {
                "input_data": df_new,
                "school_data": df_school_,
                "left_on": ref_map[ref]['join_keys'],
                "right_on": base_join_keys + [YEAR_COL],
                "prefix": f"{prefix}_{ref}" if not prefix.endswith('_') else f"{prefix}{ref}",
                "lag_suffix": lag_suffix,
            }
            
            df_new = _link_school_perf_data(**(link_kwargs or {}))
        
            # Verification
            year_col_with_lag = f"{prefix}_{ref}_{school_year_col}{lag_suffix}"
            year_diff = df_new[YEAR_COL].astype("Int64") - df_new[year_col_with_lag].astype("Int64")
            valid_diffs = set(year_diff.dropna().unique())
            if valid_diffs != {ref_map[ref]["lag"]}:
                raise ValueError(f"Verification failed for reference '{ref}'. The difference in years between the input data and linked school performance data is not equal to the specified lag for records.")
            else:
                df_new.drop(columns=[year_col_with_lag], inplace=True)
                
        df_new = df_new.drop(columns=[YEAR_COL])
        
        df_new.to_parquet(output_path, index=False)
        logger.info(f"Linked school performance data has been saved to {output_path}.")
        
        styled_print("School performance data linked and saved to external linking directory.", colour='magenta')
        
        return df_new

    #############################################
    # Append IoD and IMD features
    #############################################
    
    def add_iod(
        self,
        col_pd: str,
        input_path: Union[str, Path] = None,
        input_data: pd.DataFrame = None,
        output_dir: Union[str, Path] = None,
        output_name: str = "linked_data_with_iod.parquet",
        iod_version: int = 2019,
        df_onspd: pd.DataFrame = None,
        df_iod: pd.DataFrame = None,
        col_onspd_pcd: str = ExtRefs.ONSPD_PCD_COL,
        col_onspd_oa: str = ExtRefs.ONSPD_OA11_COL,
        col_iod_oa: str = None,
        col_imd: str = None,
        col_iod_score_tag: str = ExtRefs.IOD_SCORE_TAG,
        prefix: str = None,
        overwrite: bool = None
    ) -> pd.DataFrame:
        
        log_with_border(logger, f"Adding IoD features (version {iod_version})")
        
        if overwrite is None:
            overwrite = self.overwrite
        
        prefix = prefix or self.prefix["external"]
        
        output_dir = set_default_path(output_dir, self.link_data_dir)
        output_path = output_dir / output_name
        
        if output_path.exists() and not overwrite:
            logger.info(f"IoD features already exist at {output_path}. Skipping IoD feature addition.")
            df = load_dataframe(output_path)
            return df
        
        df_input = resolve_dataframe(
            df=input_data,
            path=input_path,
            default_path=self.input_data_path,
            name="input data",
            logger=logger
        )
        
        df_new = _add_iod(
            input_data=df_input,
            col_pd=col_pd,
            iod_version=iod_version,
            df_onspd=df_onspd,
            df_iod=df_iod,
            col_onspd_pcd=col_onspd_pcd,
            col_onspd_oa=col_onspd_oa,
            col_iod_oa=col_iod_oa,
            col_imd=col_imd,
            col_iod_score_tag=col_iod_score_tag,
            prefix=f"{prefix}_" if not prefix.endswith('_') else prefix,
        )
        
        df_new.to_parquet(output_path, index=False)
        logger.info(f"IoD features have been added and saved to {output_path}.")
        
        styled_print("IoD features added and saved to external linking directory.", colour='magenta')
                    
        return df_new
    
    #############################################
    # Derive ethnicity and gender features
    #############################################
    
    def derive_features(
        self,
        input_data: pd.DataFrame = None,
        input_path: Union[str, Path] = None,
        output_dir: Union[str, Path] = None,
        overwrite: bool = None,
        prefix: str = None,
        stud_id_col: str = STUD_ID_COL,
        derive_ethnicity: bool = True,
        derive_gender: bool = True,
        derive_school: bool = True,
        derive_language: bool = True,
        ethnicity_kwargs: dict = None,
        gender_kwargs: dict = None,
        school_kwargs: dict = None,
        language_kwargs: dict = None,
    ):
        ethnicity_kwargs = ethnicity_kwargs or {}
        gender_kwargs = gender_kwargs or {}
        
        prefix = prefix or self.prefix["derived"]
        
        if overwrite is None:
            overwrite = self.overwrite
        
        output_dir = set_default_path(output_dir, self.derive_data_dir)
        output_path = output_dir / self.save_data_name
        
        if output_path.exists() and not overwrite:
            df = load_dataframe(output_path)
            logger.info(
                f"Found existing data at {output_path}. This data will be used for feature derivation. "
                f"New devrived features will be added to this data if they do not already exist. "
                f"If you want to use different input data or a different path, provide it and set "
                f"'overwrite=True' to overwrite the existing file at {output_path}."
            )
        else:
            df = resolve_dataframe(
                df=input_data,
                path=input_path,
                default_path=self.input_data_path,
                name="input data",
                logger=logger
            )
            
        # Check derived feature flags
        prefix_dict = {
            "gender": f"{prefix}_gender",
            "ethnic": f"{prefix}_ethnicity",
            "school": f"{prefix}_sch",
            "language": f"{prefix}_language",
        }
        ethnic_derived_flag = any(prefix_dict["ethnic"] in x.lower() for x in df.columns)
        gender_derived_flag = any(prefix_dict["gender"] in x.lower() for x in df.columns)
        school_derived_flag = any(prefix_dict["school"] in x.lower() for x in df.columns)
        lan_derived_flag = any(prefix_dict["language"] in x.lower() for x in df.columns)
        
        requested_flags = [
            flag for requested, flag in [
                (derive_ethnicity, ethnic_derived_flag),
                (derive_gender, gender_derived_flag),
                (derive_school, school_derived_flag),
                (derive_language, lan_derived_flag)
            ]
            if requested
        ]
        
        # Backup existing output file
        if output_path.exists() and not overwrite:
            if requested_flags and all(requested_flags):
                logger.info(f"Data with derived features already exist at {output_path}. Skipping derivation.")
                return df
            else:
                # rename the file stored in output_path as a backup
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = output_path.with_name(f"{output_path.stem}_backup_{ts}{output_path.suffix}")
                output_path.rename(backup_path)
                logger.warning(
                    f"Existing file at {output_path} has been renamed to {backup_path} to avoid overwriting. "
                    f"Derivation will proceed and save a new file to {output_path}."
                )
      
        if derive_ethnicity and not ethnic_derived_flag:
            df_new = derive_ethnic_features(
                df.copy(), 
                prefix=prefix_dict["ethnic"],
                stud_id_col=stud_id_col,
                **ethnicity_kwargs
            )

        if derive_gender and not gender_derived_flag:
            df_new = derive_gender_features(
                df_new.copy() if vars().get("df_new") is not None else df.copy(), 
                prefix=prefix_dict["gender"],
                stud_id_col=stud_id_col,
                **gender_kwargs
            )
        
        if derive_school and not school_derived_flag:
            df_new, type_map_df, dup_stud_ids = derive_school_features(
                df_new.copy() if vars().get("df_new") is not None else df.copy(), 
                prefix=prefix_dict["school"],
                stud_id_col=stud_id_col,
                **school_kwargs
            )
            
            type_map_df.to_excel(output_dir / 'school_type_mapping.xlsx', index=False)
        
        if derive_language and not lan_derived_flag:
            df_new = derive_language_features(
                df_new.copy() if vars().get("df_new") is not None else df.copy(), 
                prefix=prefix_dict["language"],
                stud_id_col=stud_id_col,
                **language_kwargs
            )
            
        df_new.to_parquet(output_path, index=False)
        
        logger.info(f"Derived features have been saved to {output_path}.")
        
        styled_print("Data derivation process completed.", colour='magenta')
        
        return df_new

    #############################################
    # Resolve conflicts and consolidate records 
    # for each individual
    #############################################
    
    def resolve_conflicts(
        self,
        input_data: pd.DataFrame = None,
        input_path: Union[str, Path] = None,
        output_dir: Union[str, Path] = None,
        prefix_map: dict = CATEGORY_PREFIX_MAP,
        group_keys: dict = None,
        stud_id_col: str = STUD_ID_COL,
        use_conflict_ids: bool = True,
        overwrite: bool = None,
    ):
        
        log_with_border(logger, "Resolving Conflicts")
        
        if overwrite is None:
            overwrite = self.overwrite
        
        output_dir = set_default_path(output_dir, self.agg_data_dir)
        output_path = output_dir / self.save_data_name
        conflict_output_path = output_dir / "conflict.yaml"
        
        if output_path.exists() and not overwrite:
            logger.info(f"Conflict aggregation already exists at {output_path}. Skipping aggregation.")
            df_new = load_dataframe(output_path)
            return df_new
        else:
            logger.debug(f"Conflict aggregation will be saved to {output_path}. {'If this file already exists, it will be overwritten.' if overwrite else 'If this file already exists, it will not be overwritten.'}")
        
        
        df = resolve_dataframe(
            df=input_data,
            path=input_path,
            default_path=self.input_data_path,
            name="input data",
            logger=logger
        )
        
        # df = load_dataframe(input_path).copy(deep=True)
        
        if group_keys is None:
            group_keys = [col for col in df.columns if col == STUD_ID_COL or col in vars(MergeMetadata).values()]
        
        prefix_map = CATEGORY_PREFIX_MAP.copy()
        prefix_map.update(self.prefix)
        
        df_new = _resolve_conflicts(
            input_data=df,
            conflict_output_path=conflict_output_path,
            group_keys=group_keys,
            prefix_map=prefix_map,
            stud_id_col=stud_id_col,
            use_conflict_ids=use_conflict_ids,
            overwrite=overwrite
        )
        
        df_new.to_parquet(output_path, index=False)
        
        logger.info(f"Conflict resolution and data consolidation completed. Resolved data has been saved to {output_path}.")
        
        styled_print("Conflict resolution and data consolidation completed.", colour='magenta')
            
        return df_new
    
