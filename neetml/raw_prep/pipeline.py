import pandas as pd
from pathlib import Path
from typing import Union, List, Literal, Dict
from rich import print

from ..utils.misc import (
    load_dataframe, 
    parse_yaml, 
)

from ..utils.constants import (
    DATA_MANIFEST_PATH,
    DATA_PATHS,
    FileMetadata,
    STUD_ID_COL,
)

from ..utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from ._utils import (
    validate_file_naming_format,
)

from ..utils.misc import set_default_path 

from .modules.metadata import (
    extract_file_metadata as _extract_file_metadata,
    extract_file_meta_from_dir as _extract_file_meta_dir,
    add_col_info as _add_col_info,
    curate_col_dtype as _curate_col_dtype,
)

from .modules.naming import (
    standardise_fnames_colnames as _std_fnames_colnames,
)

from .modules.validation import validate_files_and_colnames as _val_files_and_colnames

from .modules.cleaning import clean_data as _clean_data

from .modules.profiling import create_data_profiling as _gen_profile

from .modules.merging import merge_data as _merge_data

from .modules.aggregation import aggregate_data as _aggregate_data

import warnings
warnings.filterwarnings("ignore")
# pd.set_option('future.no_silent_downcasting', True)

logger = get_logger("data_processor")

class RawDataCurator:
    def __init__(
        self,
        src_data_dir: Union[str, Path] = None,
        src_meta_dir: Union[str, Path] = None,
        ext_data_dir: Union[str, Path] = None,
        src_colstd_dir: Union[str, Path] = None,
        proc_data_dir: Union[str, Path] = None,
        file_metadata_path: Union[str, Path] = None,
        col_metadata_path: Union[str, Path] = None,
        data_manifest_path: Union[str, Path] = None,
        clean_dir: str = "1_cleaned",
        merge_dir: str = "2_merged",
        # agg_dir: str = "3_aggregated", # move to feature_engineering pipeline
        overwrite: bool = False,
        file_naming_format: list = None,
    ):
        """
        Initializes the RawDataCurator class with specified directories for source data, metadata, external data, and processed data, as well as file naming format and overwrite settings.
        
        Parameters
        ----------
        - src_data_dir: Directory for source data files (e.g., raw downloaded datasets).
        - src_meta_dir: Directory for source metadata files (e.g., data dictionaries, codebooks).
        - ext_data_dir: Directory for external data sources (e.g., IoD, IMD datasets).
        - src_colstd_dir: Directory for raw data with standardised column names.
        - proc_data_dir: Directory for processed data outputs (e.g., cleaned datasets, merged datasets).
        - file_metadata_path: Path to the file metadata Excel or CSV file.
        - col_metadata_path: Path to the column metadata Excel file.
        - data_manifest_path: Path to the YAML file containing data manifest and configuration.
        - clean_dir: Subdirectory name for cleaned data within the processed data directory.
        - merge_dir: Subdirectory name for merged data within the processed data directory.
        # - agg_dir: Subdirectory name for aggregated data within the processed data directory.
        - overwrite: Whether to overwrite existing files when saving outputs.
        - file_naming_format: The order of components in the filename.
            Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
            Default: ["cohort_y11_ay", "data_category" , "cohort_yg_ay", "year_group"].
        """
        
        paths = {
            "data_manifest_path": data_manifest_path,
            "file_metadata_path": file_metadata_path,
            "col_metadata_path": col_metadata_path,
            "src_data_dir": src_data_dir,
            "src_meta_dir": src_meta_dir,
            "ext_data_dir": ext_data_dir,
            "src_colstd_dir": src_colstd_dir,
            "proc_data_dir": proc_data_dir,
        }
        
        for key, user_path in paths.items():
            default_value = DATA_MANIFEST_PATH if key == "data_manifest_path" else DATA_PATHS[key.upper()]
            setattr(self, key, set_default_path(user_path, default_value))
      
        subfolders = {
            "clean_data_dir": clean_dir,
            "merge_data_dir": merge_dir,
            # "agg_data_dir": agg_dir,
            "profile_dir": "profiles",
        }       
        
        for key, folder in subfolders.items():
            default_value = DATA_PATHS[key.upper()] if key.upper() in DATA_PATHS else folder
            setattr(self, key, set_default_path(self.proc_data_dir / folder, default_value))
        
        for path in subfolders.values():
            (self.proc_data_dir / path).mkdir(parents=True, exist_ok=True)

        self.overwrite = overwrite
        
        self.file_naming_format = (
            file_naming_format 
            if file_naming_format 
            else ["cohort_y11_ay", "data_category", "year_group"]
        )

        # Extract replacement rules from the configuration
        self.data_manifest = parse_yaml(self.data_manifest_path)
        self.standardise_rules = self.data_manifest['standardise_colnames_rule'].get('standardise_rules', [])
        
        self.valid_data_categories = [
            key for key in self.data_manifest.keys()
            if not self.data_manifest[key].get("is_meta", True) and key != FileMetadata.EXCLUDE
        ] # or use DATA_CATEGORIES

    #############################################
    # Utility Functions
    #############################################
    
    def get_data_path(
        self, 
        keys: Union[
            Literal["data_config", "file_metadata", "col_metadata", "source", "source_metadata", 
                    "source_colstd", "clean", "merged", "profiles", "all"],
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
            - "data_config": Data manifest path.
            - "file_metadata": File metadata path.
            - "col_metadata": Column metadata path.
            - "source": Source data directory.
            - "source_metadata": Source metadata directory.
            - "source_colstd": Raw data with standardised column names directory.
            - "clean": Cleaned data directory.
            - "merged": Merged data directory.
            - "aggregated": Aggregated data directory.
            - "profiles": Profile data directory.
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
            "data_config": (self.data_manifest_path, "YAML file for data manifest and configuration"),
            "file_metadata": (self.file_metadata_path, "Excel file containing file-level metadata"),
            "col_metadata": (self.col_metadata_path, "Excel file containing column-level metadata"),
            "source": (self.src_data_dir, "Folder where source downloaded data are stored"),
            "source_metadata": (self.src_meta_dir, "Folder for source metadata files"),
            "source_colstd": (self.src_colstd_dir, "Folder for raw data with standardised column names"),
            "clean": (self.clean_data_dir, "Folder for cleaned and validated datasets"),
            "merged": (self.merge_data_dir, "Folder for merged datasets after linkage"),
            # "aggregated": (self.agg_data_dir, "Folder for aggregated datasets"),
            "profiles": (self.profile_dir, "Folder for profiled or derived data products"),
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

    def set_file_naming_format(
        self,
        file_naming_format: list,
    ) -> None:
        """
        Set the file naming format.
        
        Parameters
        ----------
        file_naming_format : list, optional
            The order of components in the filename. 
            Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
            Default: ["cohort_y11_ay", "data_category" , "cohort_yg_ay", "year_group"].
        
        Return
        -------
        None
        
        """
        
        self.file_naming_format = validate_file_naming_format(file_naming_format)
        
        # Create the placeholder format for logging
        format_string = "_".join([f"{{{component}}}" for component in self.file_naming_format]) + ".xlsx"
        logger.info(f"The standardised filename format is set as: {format_string}")
    
    def get_file_naming_format(
        self,
    ):
        """Return the file_naming_format."""
        return self.file_naming_format
    
    #############################################
    # STEP 1: Generate Metadata for Each File   
    #############################################    
    
    def extract_file_meta_from_dir(
        self, 
        folder_path: Union[str, Path],
        file_naming_format: list = None,
    ) -> pd.DataFrame:
        """
        Generate a file metadata DataFrame by extracting details from standardised file names.

        Parameters
        ----------
        folder_path : Union[str, Path]
            The path to the folder containing the standardised files.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing file information extracted from file names.
        """
        
        if file_naming_format is None:
            file_naming_format = self.file_naming_format
        else:
            file_naming_format = validate_file_naming_format(file_naming_format)
        
        df = _extract_file_meta_dir(
            folder_path=folder_path,
            file_naming_format=file_naming_format
        )
        
        return df
    
    def extract_file_metadata(
        self,
        folder_path: Union[str, Path] = None,
        yaml_file_path: Union[str, Path] = None,
        output_path: Union[str, Path] = None,
        overwrite: bool = None,
        display_upload_status: bool = True,
        has_processed: bool = False
    ) -> pd.DataFrame:
        """
        Generate a file metadata DataFrame with detailed information about each
        file and sheet

        Parameters
        ----------
        folder_path : Union[str, Path]
            The path to the folder containing the files to be processed.
        
        yaml_file_path : Union[str, Path]
            The path to the YAML configuration file.
        
        output_path : Union[str, Path]
            The path where the output file metadata DataFrame should be saved.
        
        display_upload_status : bool, optional
            Whether to display the upload status summary. Defaults to True.
        
        has_processed : bool, optional
            Whether the files have been processed already. Defaults to False.
        
        overwrite : bool, optional
            Flag indicating whether to overwrite the existing file metadata file, by default False.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing detailed information about each file and sheet.

        Notes
        -----
        This function processes files in the specified folder according to the rules defined
        in the YAML configuration file. It generates a DataFrame with detailed information 
        about each file and sheet, including:

        - Data Category: Assigned based on the existence of keywords in the file name or sheet name.
        - Y11 Cohort: The cohort of students in Year 11.
        - Sheet Name: The name of the sheet within the file.
        - Year Group: The school year the data was recorded for (e.g., 9 for Year 9).
        - Year Cohort: The cohort year the data pertains to (e.g., 2016-2017 for the cohort's Year 9 data).
        - Uncurated Year Group and Cohort: The initial, uncurated values of Year
          Group and Cohort based on corresponding file/sheet name.

        If an existing file metadata file is found and overwrite is set to False, this function 
        will append new information to the existing file metadata rather than overwriting it.
        """
        
        log_with_border(logger, "Starting extracting file metadata")
        
        folder_path = set_default_path(folder_path, self.src_data_dir)
        yaml_file_path = set_default_path(yaml_file_path, self.data_manifest_path)
        output_path = set_default_path(output_path, self.file_metadata_path)

        if overwrite is None:
            overwrite = self.overwrite
        
        df, cat_summary = _extract_file_metadata(
            folder_path=folder_path,
            yaml_file_path=yaml_file_path,
            output_path=output_path,
            overwrite=overwrite,
            valid_cat=self.valid_data_categories,
            display_upload_status=display_upload_status,
            has_processed=has_processed
        )

        return df, cat_summary
    
    #############################################
    # STEP 2: Standardise File Names and Columns
    #############################################
    
    def standardise_fnames_colnames(
        self,
        input_path: Union[str, Path] = None,
        output_path: Union[str, Path] = None,
        file_metadata: pd.DataFrame = None,
        file_metadata_path: Union[str, Path] = None,
        col_metadata_path: Union[str, Path] = None,
        file_naming_format: list = None,
        add_prefix: bool = True,
        overwrite: bool = None
    ) -> None:
        """
        Standardises file names and column names based on standardise_colnames_rule in YAML file.

        Parameters
        ----------
        input_path : Union[str, Path], optional
            Path to the folder containing the source data files.
        
        output_path : Union[str, Path], optional
            Path to the folder where the standardised files will be saved.
        
        file_metadata : pd.DataFrame, optional
            DataFrame containing metadata about each file, including details like source 
            and standardised file names, sheet names, and other metadata attributes.
        
        file_metadata_path : Union[str, Path], optional
            Path to a CSV or XLSX file containing file metadata. If provided, this file is 
            loaded into `file_metadata` for use within the function.
            
        col_metadata_path : Union[str, Path], optional
            Path to the output Excel file where column metadata, including both source 
            and standardised column names, will be saved or updated.
        
        file_naming_format : list, optional
            The order of components in the filename. 
            Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
            Default: ["cohort_y11_ay", "data_category" , "year_group"].
        
        add_prefix: bool, optional
            If True, adds the corresponding data category as a column prefix when standardising column names. 

        overwrite : bool, optional
            If True, allows overwriting of existing files in `output_path`. If False, 
            skips files that already exist, preventing overwriting.

        Returns
        -------
        None
        
        """

        log_with_border(logger, "Standardising filenames and column names...")

        input_path = set_default_path(input_path, self.src_data_dir)
        output_path = set_default_path(output_path, self.src_colstd_dir)
        file_metadata_path = set_default_path(file_metadata_path, self.file_metadata_path)
        col_metadata_path = set_default_path(col_metadata_path, self.col_metadata_path)

        if file_metadata is None and file_metadata_path is not None:
            logger.info(f"{file_metadata_path} loaded.")
            file_metadata = load_dataframe(file_metadata_path)
        elif file_metadata is None:
            file_metadata = self.extract_file_meta_from_dir(input_path)

        if overwrite is None:
            overwrite = self.overwrite
        
        if file_naming_format is None:
            # If no format is provided, use the default file naming format from the instance
            file_naming_format = self.file_naming_format
        else:
            # If a format is provided, validate and set it as the new file naming format for the instance
            self.file_naming_format = self.set_file_naming_format(file_naming_format)
        
        _ = _std_fnames_colnames(
            input_path=input_path,
            output_path=output_path,
            file_metadata=file_metadata,
            file_metadata_path=file_metadata_path,
            col_metadata_path=col_metadata_path,
            file_naming_format=file_naming_format,
            add_prefix=add_prefix,
            overwrite=overwrite,
            standardise_rules=self.standardise_rules,
            valid_cat=self.valid_data_categories
        )
        
        return None

    #############################################
    # STEP 4: Pre-Cleaning Validation
    #############################################
    
    def validate_files_and_colnames(
        self,
        folder_path: Union[str, Path],
        validate_dup_file: bool = True,
        common_cols_threshold: float = 0.8,
    ) -> None:
        """
        Validate the data in the folder for column name consistency and duplicate data.
        
        Parameters
        ----------
        folder_path : Union[str, Path]
            The path to the folder containing the data files to be validated.
            
        validate_dup_file : bool, optional, default=True
            Whether to validate for duplicate data files. If True, the function will check for duplicate files
            based on file content (e.g., hash comparison).
        
        common_cols_threshold : float, optional, default=0.8
            A threshold defining the minimum proportion of files that must share the same column name for it
            to be considered "common". This value should be between 0 and 1. For example, a value of 0.8 means
            that a column must appear in at least 80% of the files to be considered common.
        
        Returns
        -------
        None
        """
        
        log_with_border(logger, "Starting pre-cleaning or post-cleaning validation...")
        
        folder_path = Path(folder_path)
        
        # Extract metadata for all files in the folder
        file_metadata = self.extract_file_meta_from_dir(folder_path)
        
        _ = _val_files_and_colnames(
            file_metadata=file_metadata,
            folder_path=folder_path,
            validate_dup_file=validate_dup_file,
            common_cols_threshold=common_cols_threshold,
        )
        
        return None
        
    #############################################
    # STEP 5: Data Cleaning
    #############################################
    
    def clean_data(
        self,
        input_path: Union[str, Path] = None,
        stud_id_col: str = STUD_ID_COL,
        rm_nan_stud_id: bool = True,
        rm_nan_cols_threshold: Union[Literal[False], float] = 0.5,
        rm_dups_threshold: Union[Literal[False],
                                           float, Literal['first']] = False,
        rm_empty_cols: bool = True,
        rm_constant_cols: Union[Literal[False], Literal['global'], Literal['local']] = 'local',
        constant_consistency: float = 0.8,
        consider_missing: bool = False,
        missing_cutoff: float = 0.8,
        rm_problematic_ids: Union[Literal[False], int, List[int]] = False,
        rm_sensitive_cols: List[str] = None,
        output_path: Union[str, Path] = None,
        col_metadata_path: Union[str, Path] = None,
        overwrite: bool = None
    ) -> None:
        """
        Clean the data by performing the following actions:
        - Read all .xlsx / .csv files from the specified or default raw data path.
        - Remove duplicates and NaN values based on the given thresholds.
        - Remove specified sensitive columns if they exist in the data.
        - Save the cleaned data to the output directory.

        Parameters
        ----------
        input_path : Union[str, Path], optional
            Path to the directory containing the raw data files. Uses default path if not provided.
        
        stud_id_col : str, optional
            Name of the column containing student IDs. Defaults to 'stud_id'.
        
        rm_nan_stud_id : bool, optional
            If True, removes rows with NaN 'stud_id' values. Default is True.
        
        rm_nan_cols_threshold : Union[Literal[False], float], optional
            If set, removes columns with a higher proportion of NaN values than the threshold. 
            Set to False to skip this. Default is 0.5.
        
        rm_dups_threshold : Union[Literal[False], float, Literal['first']], optional
            If 'first', keeps the first instance of duplicates. If a float, removes duplicates
            if the percentage of NaN values in a duplicate row exceeds this threshold. Default is False.
        
        rm_empty_cols : bool, optional
            If True, removes columns with all NaN values. Default is True.
        
        rm_problematic_ids : Union[Literal[False], int, List[int]], optional
            List of specific student IDs to remove from the data. Default is False (no IDs removed).
        
        rm_constant_cols : Union[False, 'global', 'local'], optional
            Specifies whether to remove columns with constant values:
            - False: Do not remove constant columns.
            - 'global': Remove columns that have a single constant value across all files in the folder.
            - 'local': Remove columns that have a single constant value within each file individually.
        
        constant_consistency : float, optional
            The minimum fraction of files in which a column must have a single 
            dominant constant value for it to be considered globally constant.
            Only valid if rm_constant_cols = 'global'.
            Default is 0.8 (80%).
        
        missing_cutoff : float, optional
            The maximum allowed fraction of missing values in the global distribution 
            of a variable. If the proportion of "Missing" values is equal to or greater 
            than this cutoff and missing filtering is enabled, the variable is excluded.
            Only valid if rm_constant_cols = 'global' and consider_missing = True.
            Default is 0.8 (80%).
            
        consider_missing : bool, optional
            If True (default), apply missing filtering based on `missing_cutoff`.
            If False, do not filter out variables based on missing values.
            Only valid if rm_constant_cols = 'global'.
        
        sensitive_cols : List[str], optional
            List of column names that contain sensitive information (e.g., 'surname', 'forename')
            and should be removed from the dataset if present. Default is None.
        
        output_path : Union[str, Path], optional
            Path to the directory where cleaned data will be saved. Uses default path if not provided.
        
        col_metadata_path : Union[str, Path], optional
            Path to save column metadata after cleaning. Uses default path if not provided.
        
        overwrite : bool, optional
            If True, existing cleaned files are overwritten. Uses default setting if not provided.

        Returns
        -------
        None
        """
        
        log_with_border(logger, "Starting the data cleaning process...")
    
        input_path = set_default_path(input_path, self.src_colstd_dir)
        output_path = set_default_path(output_path, self.clean_data_dir)
        col_metadata_path = set_default_path(col_metadata_path, self.col_metadata_path)
        
        if overwrite is None:
            overwrite = self.overwrite
        
        _ = _clean_data(
            input_path=input_path,
            stud_id_col=stud_id_col,
            rm_nan_stud_id=rm_nan_stud_id,
            rm_nan_cols_threshold=rm_nan_cols_threshold,
            rm_dups_threshold=rm_dups_threshold,
            rm_empty_cols=rm_empty_cols,
            rm_constant_cols=rm_constant_cols,
            constant_consistency=constant_consistency,
            consider_missing=consider_missing,
            missing_cutoff=missing_cutoff,
            rm_problematic_ids=rm_problematic_ids,
            rm_sensitive_cols=rm_sensitive_cols,
            output_path=output_path,
            col_metadata_path=col_metadata_path,
            file_naming_format=self.file_naming_format,
            overwrite=overwrite
        )
        
        return None
    
    #############################################
    # OPTION STEP: Curate Metadata for Columns
    #############################################
    
    def add_col_info(
        self,
        col_metadata: Dict[str, pd.DataFrame] = None,
        yaml_data: Dict[str, Dict[str, Union[str, List[Dict[str, str]]]]] = None,
        input_path: Union[str, Path] = None,
        output_path: Union[str, Path] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Append descriptions and values information to each sheet in col_metadata from multiple metadata sources.
        Adds a suffix from the nickname if there are multiple sources, but removes duplicates if identical.

        Parameters
        ----------
        col_metadata : dict, optional
            Dictionary where keys are sheet names and values are DataFrames of the column metadata for each category.
            If not provided, loads from self.col_metadata_path.
                    
        yaml_data : dict, optional
            Dictionary containing metadata file information and mappings for additional columns.
            If not provided, uses self.config_data.
            Example structure:
                attendance:  # Data category
                  is_meta: False
                  metadata:
                    sources:
                      - filename: School data metadata (census, attendance, exclusions).xlsx
                        sheetname: Attendance
                        colname: Field
                        description: Info
                        value: Values
                    
        input_path : Union[str, Path], optional
            Directory containing the metadata files. Defaults to self.src_meta_dir if not provided.
            
        output_path : Union[str, Path], optional
            Path where the Excel file should be saved.

        Returns
        -------
        dict
            Updated col_metadata with appended description and values information for each sheet.
        """
        
        # Set the default path if not provided
        input_path = set_default_path(input_path, self.src_meta_dir)
        output_path = set_default_path(output_path, self.col_metadata_path)
        
        # Load col_metadata if not provided
        if col_metadata is None:
            col_metadata = pd.read_excel(self.col_metadata_path, sheet_name=None)
        
        # Use default yaml_data if not provided
        if yaml_data is None:
            yaml_data = self.data_manifest
        
        col_metadata = _add_col_info(
            col_metadata=col_metadata,
            yaml_data=yaml_data,
            input_path=input_path,
            output_path=output_path,
        )
            
        return col_metadata
    
    # not necessay especially when using df = df.convert_dtypes(dtype_backend="pyarrow")
    def curate_col_dtype(
        self,
        col_metadata: Dict[str, pd.DataFrame] = None,
        output_path: Union[str, Path] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Curate the data types for specified columns in col_metadata and update with curated data types.
        Highlight cells in the "Curated Data Type" column if they differ from "Uncurated Data Type".

        Parameters
        ----------
        col_metadata : dict
            Dictionary where keys are sheet names and values are DataFrames of the column metadata for each category.

        output_path : Union[str, Path], optional
            Path where the updated Excel file should be saved. Defaults to self.col_metadata_path.

        Returns
        -------
        dict
            Updated col_metadata with curated data types and additional metadata columns.
        """
        
        if col_metadata is None:
            col_metadata = pd.read_excel(self.col_metadata_path, sheet_name=None)
        
        output_path = set_default_path(output_path, self.col_metadata_path)
        
        col_metadata = _curate_col_dtype(
            col_metadata=col_metadata,
            standardise_rules=self.standardise_rules,
            output_path=output_path
        )
        
        return col_metadata
    
    #############################################
    # OPTION STEP: Generate Data Profiling
    #############################################
    
    def create_data_profile(
        self,
        df: pd.DataFrame = None,
        folder_path: Union[str, Path] = None,
        data_schema: Dict[str, pd.DataFrame] = None,
        minimal: bool = True,
        explorative: bool = False,
        progress_bar: bool = False,
        title: str = None,
        output_prefix: str = None,
    ) -> None:
        """
        Generate a data profiling report using either a pandas DataFrame or by processing all xlsx / csv files 
        in a specified folder. The profiling reports can be generated in minimal or full mode, 
        and can be explorative.
        
        Parameters:
        -----------
        df : pd.DataFrame, optional
            The pandas DataFrame to be profiled. If None, folder_path should be provided.
            
        folder_path : str or Path, optional
            The folder containing CSV or XLSX files to be profiled. Only one of df or folder_path
            should be provided.
        
        data_schema: Dict[str, pd.DataFrame]
            The schema containing curated data types.
        
        minimal : bool, default True
            If True, generates a minimal data profile (quick summary). If False, generates a 
            full profiling report with deeper insights and visualisations.
            
        explorative : bool, default False
            If True, generates an explorative profile that includes more advanced analysis, such as 
            correlations and interactions between variables. If False, a standard profile is created.
            
        progress_bar : bool, default False
            Whether to show a progress bar during profiling.
            
        title : str, optional
            The title for the profiling report.
            
        output_prefix : str, optional
            The prefix to be added to the output file names. If not provided, defaults to "data_profile". 
            This is useful when generating multiple reports to distinguish them.
            
        Returns:
        --------
        None
            Generates and saves the profiling reports to the specified profile path.
            
        Example Usage:
        --------------
        1. Generating a profiling report for a single DataFrame:
        
            create_data_profiling(df=my_dataframe, minimal=True, title="Data Profile")

        2. Generating reports for all CSV/XLSX files in a folder:
        
            create_data_profiling(folder_path="path/to/folder", minimal=False, title="Dataset Profiles")
        """
        
        log_with_border(logger, "Starting data profiling...")

        # Ensure that either df or folder_path is provided, but not both or none
        if (df is None and folder_path is None) or (df is not None and folder_path is not None):
            raise ValueError("Please provide either a pandas DataFrame or a path to the folder, but not both.")
        
        if data_schema is None:
            data_schema = pd.read_excel(self.col_metadata_path, sheet_name=None)
        
        if output_prefix is None:
            output_prefix = "data_profile"

        _ = _gen_profile(
            df=df,
            folder_path=folder_path,
            data_schema=data_schema,
            profile_dir=self.profile_dir,
            minimal=minimal,
            explorative=explorative,
            progress_bar=progress_bar,
            title=title,
            output_prefix=output_prefix
        )

        return None
    
    #############################################
    # STEP 6: Merge Datasets
    # Note: This step does not alter the source 
    # data values. It simply consolidates data 
    # from different sources into a unified format.
    #############################################
    
    def merge_data(
        self,
        stud_id_col: str = STUD_ID_COL,
        nccis_append_start_yg: int = 11,
        input_path: Union[str, Path] = None,
        use_file_metadata: Union[str, Path, None, Literal[False]] = None,
        data_schema: Dict[str, pd.DataFrame] = None,
        output_path: Union[str, Path] = None,
        group_by: Literal["cohort_yg_ay", "cohort_y11_ay"] = "cohort_yg_ay",
        group_sim_cutoff: float = 0.7,
        group_subset_cutoff: float = 0.5,
        grouping_strategy: Literal["flexible", "strict"] = "strict",
        save_tmp_outputs: bool = False,
        overwrite: bool = False,
    ) -> None:
        """
        Merge data by Cohort using 'stud_id' and if needed, one additional school-related column pair.
        
        The merging logic is as follows:
        1. Start with one dataset and iteratively merge others in the same Cohort.
        2. Attempt to merge on 'stud_id' alone. If that isn't sufficient, try predefined candidate pairs 
           of school-related columns to find a unique match key. Choose the key that yields the most matches.
        3. After merging, reorder columns and remove identical duplicate rows (based on all columns except 'stud_id').
        
        If group_by="cohort_yg_ay":
          1. Merge all files that do not have a Cohort (e.g. 'sepGuarantee').
          2. Merge all files by Cohort, then save each Cohort's result directly to output_path.
             (The parameter save_tmp_outputs is inconsequential here, unless
              you want to separate them into a subfolder. You can adjust as needed.)

        If group_by="cohort_y11_ay":
          1. Merge all files by Y11 Cohort.
             - If save_tmp_outputs=True:
                 * Save each Cohort-level merged file to 'intermediate/' folder under output_path.
                 * Optionally also keep them in memory (all_data). Or you can skip that.
             - If save_tmp_outputs=False:
                 * Keep all merged results in memory only (all_data), do not write them.
          2. If we reach the Y11 Cohort merging step but all_data is empty:
             - Attempt to read all Cohort files from the 'intermediate/' folder. 
               (This implies we rely on the user having set save_tmp_outputs=True.)
          3. Merge across all Y11 Cohort-level data frames by Year Group, generating the final files.
          
        NOTE:
            The NCCIS `nccis_code` from the March extract is appended to the pre-16 dataset.

            Starting from Year 11, we begin generating post-16 (Year 11+) longitudinal records. 
            This stage links Year 11 school-based performance data (e.g., Attendance, Exclusions, KS2 outcomes, KS4 outcomes) 
            with NCCIS participation data for young people aged 16-24.

            Each academic age is modelled in two sequential phases:

            ▸ **Phase 1 (September → March)**  
            - NCCIS September data is merged and treated as the training-period predictor set.  
            - NCCIS March data is used as the outcome/target label for the same cohort.  

            ▸ **Phase 2 (March → next September)**  
            - NCCIS March data replaces September data as the new predictor set.  
            - The next academic year's September NCCIS extract becomes the target.  

        Parameters
        ----------
        stud_id_col: str, optional
            The column name for student ID in the data. Defaults to 'stud_id'.

        nccis_append_start_yg : int, default 11
            The starting year group for appending NCCIS data.

        input_path : Union[str, Path], optional
            Path to the directory containing the cleaned data files. If None, uses self.clean_data_dir.
            
        use_file_metadata : Union[str, Path, None, Literal[False]], optional
            If None, uses self.file_metadata_path.
            If False, generates file_metadata from standardised file names in input_path.
            Else, load from given path.

        data_schema : Dict[str, pd.DataFrame], optional
            A mapping from Data Category names to their corresponding schema (as a DataFrame).

        output_path : Union[str, Path], optional
            Path where the merged data will be saved. If None, uses self.merge_data_dir.
            
        group_by : {"cohort_yg_ay", "year_group"}, default "cohort_yg_ay"
            - "cohort_yg_ay": stop after Cohort merges.
            - "year_group": merge by Cohort, then (optionally) load them from intermediate folder,
              merge by Year Group, and save final outputs.

        group_sim_cutoff : float, optional
            Minimum proportion of common columns to consider DataFrames as part of the same group (default is 0.7).
            Only validate if group_by="cohort_y11_ay".
        
        group_subset_cutoff : float, optional
            Minimum similarity required to merge groups where one DataFrame's columns are a strict subset of another (default is 0.5).
            Only validate if group_by="cohort_y11_ay".

        grouping_strategy : Literal["strict", "flexible", "balanced"], optional
            - "strict" (default): Groups only based on column similarity threshold.
            - "flexible": Merges groups if one DataFrame's columns are a strict subset of another.
            - "balanced": Merges groups if subset relation exists AND similarity is >= `subset_cutoff`.
            
        save_tmp_outputs : bool, default False
            If True and group_by="year_group", saves each Cohort's merged file into an 'intermediate' 
            subfolder under output_path. If later you need to load from disk (when in-memory data is empty),
            the code can retrieve them from that folder.

        overwrite : bool, default False
            Whether to overwrite existing merged files if they already exist.

        Raises
        ------
        ValueError
            - If no suitable school column pair is found for merging when 'stud_id' alone is insufficient.
            - If the merged dataset fails the post-merge validation against the source input datasets.
        """

        log_with_border(logger, "Starting data merging process...")

        # Set paths
        input_path = set_default_path(input_path, self.clean_data_dir)
        output_path = set_default_path(output_path, self.merge_data_dir)

        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)

        if data_schema is None:
            data_schema = pd.read_excel(self.col_metadata_path, sheet_name=None)

        # Load or generate file_metadata
        if use_file_metadata is None:
            file_metadata_path = self.file_metadata_path
            logger.info(f"Loading file metadata from default file_metadata_path: {file_metadata_path}...")
            file_metadata = load_dataframe(file_metadata_path)
        elif isinstance(use_file_metadata, (str, Path)):
            file_metadata_path = Path(use_file_metadata)
            logger.info(f"Loading file metadata from provided path: {file_metadata_path}...")
            file_metadata = load_dataframe(file_metadata_path)
        elif use_file_metadata is False:
            logger.warning(f"No file info provided. Generating file_metadata from {input_path}...")
            file_metadata = self.extract_file_metadata_from_folder(input_path)
        else:
            raise ValueError("Invalid use_file_metadata value.")

        _ = _merge_data(
            stud_id_col=stud_id_col,
            nccis_append_start_yg=nccis_append_start_yg,
            input_path=input_path,
            file_metadata=file_metadata,
            data_schema=data_schema,
            output_path=output_path,
            group_by=group_by,
            group_sim_cutoff=group_sim_cutoff,
            group_subset_cutoff=group_subset_cutoff,
            grouping_strategy=grouping_strategy,
            save_tmp_outputs=save_tmp_outputs,
            valid_cat=self.valid_data_categories,
            overwrite=overwrite
        )
        
        return None
    
    #############################################
    # STEP 7: Aggregate Data (Discontinued)
    #############################################
    
    def aggregate_data(
        self,
        stud_id_col: str = STUD_ID_COL,
        input_path: Union[str, Path] = None,
        output_path: Union[str, Path] = None,
        data_schema: Dict[str, pd.DataFrame] = None,
        merge_equiv_cols: bool = False,
        overwrite: bool = None,
    ) -> pd.DataFrame:
        """
        Aggregate data from files in the specified folder.

        Parameters
        ----------
        stud_id_col: str, optional
            The column name for student ID in the data. Defaults to 'stud_id'.
            
        input_path : Union[str, Path], optional
            Path to the directory containing the cleaned data files. If None, uses self.merge_data_dir.

        output_path : Union[str, Path], optional
            Path where the aggregated data will be saved. If None, uses self.aggregated_data_path.
        
        data_schema : Dict[str, pd.DataFrame], optional
            The schema containing curated data types.
      
        merge_equiv_cols : bool, optional  
            Whether to aggregate columns with different names that contain the same or complementary data.
            Defaults to False. If True, columns identified as equivalent or complementary will be merged.
        
        overwrite : bool, optional
            Whether to overwrite the existing aggregated data.

        Returns
        -------
        pd.DataFrame
            Aggregated DataFrame.

        Notes
        -----
        This function assumes that files are named in a standardised format and uses the 
        metadata to aggregate data as per the specified schema and rules.
        """

        log_with_border(logger, "Starting the data aggregation process...")

        input_path = set_default_path(input_path, self.merge_data_dir)
        output_path = set_default_path(output_path, self.agg_data_dir)

        if overwrite is None:
            overwrite = self.overwrite
        
        _ = _aggregate_data(
            stud_id_col=stud_id_col,
            input_path=input_path,
            data_schema=data_schema,
            output_path=output_path,
            merge_equiv_cols=merge_equiv_cols,
            valid_cat=self.valid_data_categories,
            overwrite=overwrite
        )

        return None
    
    #############################################
    # Auto Processing (TBD)
    #############################################
    
    # # TODO: update base on step by step guide
    # def auto_preprocessing(self):
    #     """
    #     Automatically preprocesses all data files in the data directory.
    #     """
    #     self.extract_file_metadata()
    #     self.standardise_fnames_colnames()
    #     self.clean_data(
    #         rm_nan_stud_id=True,
    #         rm_nan_cols_threshold=False,
    #         rm_empty_cols=True,
    #         rm_dups_threshold='first',
    #         # rm_problematic_ids=[471807, 534073]
    #     )
    #     self.merge_data()
