import logging
import pandas as pd
from pathlib import Path
from typing import Union, Dict
from ydata_profiling import ProfileReport


from ...utils.misc import (
    styled_print, 
    load_dataframe, 
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)


logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  

def create_data_profiling(
    df: pd.DataFrame,
    folder_path: Union[str, Path],
    profile_dir: Union[str, Path],
    data_schema: Dict[str, pd.DataFrame],
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
        The pandas DataFrame to be profiled. 
        
    folder_path : str or Path
        The folder containing CSV or XLSX files to be profiled. 
    
    profile_dir : str or Path
        The directory where the profiling reports will be saved.
        
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
    # log_with_border(logger, "Starting data profiling...")
    
    profile_dir = Path(profile_dir)    
    
    # If df is provided, generate a profiling report for the DataFrame
    if df is not None:            
        # Create and save the profiling report
        suffix = "__minimal" if minimal else ""
        profile = ProfileReport(
            df, 
            title=title, 
            minimal=minimal, 
            progress_bar=progress_bar, 
        explorative=explorative)
        
        profile.to_file(profile_dir / f"{output_prefix}{suffix}.html")

    # If folder_path is provided, process all CSV or XLSX files in the folder
    else:
        folder_path = Path(folder_path)
        file_list = list(folder_path.glob("*.csv")) + list(folder_path.glob("*.xlsx"))
        
        if len(file_list) == 0:
            raise ValueError(f"No CSV or XLSX files found in {folder_path}.")
        
        # Loop through each file in the folder
        for file_path in file_list:
            file_name = file_path.stem  # Use the file's name for the output report
            
            df = load_dataframe(file_path)
            
            if data_schema:
                df = apply_schema_to_dataframe(
                    df=df, 
                    data_category=file_name.split('_')[self.file_naming_format.index("data_category")], 
                    data_schema=data_schema,
                )
            
            # Create and save the profiling report for each file
            suffix = "__minimal" if minimal else ""
            profile = ProfileReport(
                df, 
                title=f"Data Profile of {file_name}" if title is None else title, 
                minimal=minimal, 
                progress_bar=progress_bar,
                explorative=explorative
            )
            
            profile.to_file(self.profile_dir / f"{output_prefix}__{file_name}{suffix}.html")

    styled_print("Data profiling has been completed.", colour='magenta')

    return None
    