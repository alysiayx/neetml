import logging
import pandas as pd
from pathlib import Path
from typing import Union, Dict

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    get_files_in_folder, 
    check_folder_file_count_equal,
    print_table,
)

from ...utils.constants import (
    DROP_COLS,
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from ._aggregation_utils import (
    check_agg_records,
    merge_equiv_columns,
)

from ._merging_utils import apply_schema_to_dataframe

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)   


def aggregate_data(
    stud_id_col: str,
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    data_schema: Dict[str, pd.DataFrame],
    merge_equiv_cols: bool = False,
    overwrite: bool = None,
) -> pd.DataFrame:
    """
    Aggregate data from files in the specified folder.

    Parameters
    ----------
    stud_id_col: str, optional
        The column name for student ID in the data. Defaults to 'stud_id'.
        
    input_path : Union[str, Path]
        Path to the directory containing the cleaned data files.

    output_path : Union[str, Path]
        Path where the aggregated data will be saved.

    data_schema : Dict[str, pd.DataFrame]
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

    # log_with_border(logger, "Starting the data aggregation process...")
    
    # The dictionary uses to track the aggregation summary
    aggregation_summary = {}

    if overwrite or not check_folder_file_count_equal(input_path, output_path):

        if data_schema is None:
            data_schema = pd.read_excel(self.col_metadata_path, sheet_name=None)
        
        files = get_files_in_folder(folder_path=input_path, recursive=False)
        
        files = sorted([
            # file for file in input_path.rglob("*") 
            file for file in input_path.glob("*")  # exclude subfolders' files
            if file.suffix in {".xlsx", ".csv", ".parquet"}
        ])
        
        for file_path in files:
            # Define output file path
            output_file_path = output_path / file_path.name
            
            if output_file_path.exists() and not overwrite:
                continue
            
            logger.info(f"Now Reading {file_path}...")

            df = load_dataframe(
                file_path, 
                # dtype_backend='pyarrow'
            )
            
            drop_cols = DROP_COLS.intersection(df.columns)
            if drop_cols:
                df.drop(columns=[col for col in drop_cols], inplace=True)
                logger.info(f"Removed columns: {drop_cols}")
            
            if file_path.suffix == '.xlsx':                    
                df = apply_schema_to_dataframe(
                    df=df, 
                    data_schema=data_schema,
                    is_merged=True,
                )
            
            if merge_equiv_cols:
                # Check if any columns have similar names and store the same information
                # Need few mins
                df = merge_equiv_columns(df, stud_id_col)
            
                
            df = check_agg_records(df, stud_id_col)
            
           
            raise ValueError("STOP, CHECK THE AGGREGATION RESULTS BEFORE PROCEEDING TO THE NEXT STEPS.")
            # Save the data
            df.to_excel(output_file_path, index=False)
            problematic_stud_records.to_excel(output_path.parent / "problematic_student_records.xlsx", index=False)

            log_line_break(logger)

    # Print aggregation summary
    styled_print("Aggregation Summary by Data Category:")
    aggregation_summary_df = pd.DataFrame.from_dict(aggregation_summary, orient='index')
    # aggregation_summary_df.index.name = "Data Category"
    # aggregation_summary_df.reset_index(inplace=True)
    print_table(aggregation_summary_df, group_records=False, show_index=True, num_rows='all')

    styled_print("Data aggregation process completed.", colour='magenta')

    return None
    
