import pandas as pd
import numpy as np
from pathlib import Path
import logging
from typing import Union
from tabulate import tabulate
from rich.table import Table
from rich.console import Console

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    display_columns_table, 
    similar_score, 
)

from ...utils.constants import (
    FileMetadata,
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from .._utils import compute_data_hash


import warnings
warnings.filterwarnings("ignore")
# pd.set_option('future.no_silent_downcasting', True)

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  


def validate_files_and_colnames(
    file_metadata: pd.DataFrame,
    folder_path: Union[str, Path],
    validate_dup_file: bool = True,
    common_cols_threshold: float = 0.8,
) -> None:
    """
    Validate the data in the folder for column name consistency and duplicate data.
    
    Parameters
    ----------
    file_metadata : pd.DataFrame
        DataFrame containing metadata about the files, including standardised file names and data categories.
    
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
    
    # log_with_border(logger, "Starting pre-cleaning or post-cleaning validation...")
    
    save_dir = folder_path.with_name(folder_path.name + '_colnames_val')
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Dictionary to store columns for each data category
    columns_by_category = {}
    
    # Dictionary to store data hashes for all files
    data_hashes = {}
    duplicate_files = []
    
    # Iterate through each file to collect columns and compute data hashes
    for _, file_info in file_metadata.iterrows():
        data_category = file_info[FileMetadata.CATEGORY]
        file_name = file_info[FileMetadata.STD_FILE_NAME]
        file_path = Path(folder_path) / file_name
        
        df = load_dataframe(file_path)
        df = df.dropna(axis=1, how='all')
        
        # Get columns
        columns = set(df.columns)
        if data_category in columns_by_category:
            columns_by_category[data_category].append((file_name, columns))
        else:
            columns_by_category[data_category] = [(file_name, columns)]
        
        if validate_dup_file == True:
            # Compute data hash
            data_hash = compute_data_hash(df)
            
            # Check for duplicate data hash across all files
            if data_hash in data_hashes:
                logger.warning(f"Duplicate data detected:")
                logger.warning(f"- Original file: {data_hashes[data_hash]}")
                logger.warning(f"- Duplicate file: {file_name}")
                duplicate_files.append((data_hashes[data_hash], file_name))
            else:
                data_hashes[data_hash] = file_name  # Map hash to file_name
    
    # After processing all files, check for column name consistency
    for data_category, files_columns in columns_by_category.items():
        styled_print(f"\nValidating Data Category: {data_category}")
        
        # Extract all columns for this category
        all_columns_list = [cols for _, cols in files_columns]
        # # Find all columns (union)
        # all_columns = set.union(*all_columns_list)
        
        # Count the frequency of each column
        columns_frequency = {}
        for columns in all_columns_list:
            for column in columns:
                columns_frequency[column] = columns_frequency.get(column, 0) + 1
        
        total_files = len(files_columns)
                    
        # Columns present in at least threshold% of the files
        columns_in_most_files = {
            column for column, freq in columns_frequency.items()
            if freq / total_files >= common_cols_threshold
        }
            
        # Display columns present in most files
        display_columns_table(
            columns_in_most_files,
            title=f"\nColumns present in at least {int(common_cols_threshold * 100)}% of files"
        )
        
        # # Display all columns
        # display_columns_table(all_columns, title="All columns present")
        
        save_path = save_dir / f"{data_category}_thres_{common_cols_threshold}.xlsx"
        
        table_data = []
        for file_name, columns in files_columns:
            missing_columns = columns_in_most_files - columns
            extra_columns = columns - columns_in_most_files
            
            # Only compare non-empty sets of columns
            if pd.notna(missing_columns) and pd.notna(extra_columns):
                # Apply fuzzy matching for each missing column
                matching_results = []
                for missing in missing_columns:
                    best_match = None
                    highest_similarity = 0
                    
                    # Check if the column contains a percentage sign
                    missing_contains_percent = '%' in missing
        
                    for extra in extra_columns:
                        extra_contains_percent = '%' in extra

                        # Only compare if both columns either have or do not have the percentage sign
                        if missing_contains_percent == extra_contains_percent:
                            similarity = similar_score(missing.lower(), extra.lower())
                            if similarity > highest_similarity:
                                best_match = extra
                                highest_similarity = similarity
                                
                    # Only add results where similarity score is greater than 0.5
                    if highest_similarity > 0.5:
                        matching_results.append({
                            'Missing Column': missing,
                            'Best Match in Extra Column': best_match,
                            'Similarity Score': highest_similarity
                        })
                
                # Create a string that includes the missing column and the best matching extra column with similarity score
                matching_info = '; \n'.join([f"{result['Missing Column']} -> {result['Best Match in Extra Column']} ({result['Similarity Score']:.2f})" for result in matching_results])
            else:
                matching_info = ''

            table_data.append({
                FileMetadata.STD_FILE_NAME: file_name,
                'Missing Columns': ', \n'.join(sorted(missing_columns)) if missing_columns else '',
                'Extra Columns': ', \n'.join(sorted(extra_columns)) if extra_columns else '',
                'Missing and Matched Columns (Missing -> Extra)': matching_info,
                'Number of Non-empty Columns': len(columns)
            })
        
        result_df = pd.DataFrame(table_data)
        result_df[FileMetadata.YEAR_GRP] = result_df[FileMetadata.STD_FILE_NAME].str.extract(r'_Y(\d+)-').fillna(0).astype(int)
        result_df[FileMetadata.COHORT_Y11_AY] = result_df[FileMetadata.STD_FILE_NAME].str.split('_').str[1]
        result_df.sort_values(by=[FileMetadata.COHORT_Y11_AY, FileMetadata.YEAR_GRP], inplace=True)
        result_df.drop(columns=[FileMetadata.YEAR_GRP], inplace=True)
        
        result_df.to_excel(save_path, index=False)
        
        # print(tabulate(result_df[[FileMetadata.STD_FILE_NAME, 'Number of Non-empty Columns']], headers='keys', tablefmt='fancy_outline'))
        
        console = Console(width=150)

        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Standardised File Name", no_wrap=True)
        table.add_column("Missing Columns", no_wrap=False, style="cyan")
        table.add_column("Extra Columns", no_wrap=False, style="green")
        table.add_column("Missing and Matched Columns (Missing -> Extra)", no_wrap=False, style="dark_red")
        table.add_column("Number of Non-empty Columns", no_wrap=False, style="orange1", max_width=10)

        for _, row in result_df.iterrows():
            table.add_row(str(row[FileMetadata.STD_FILE_NAME]), str(row['Missing Columns']), str(row['Extra Columns'], ), str(row['Missing and Matched Columns (Missing -> Extra)']), str(row['Number of Non-empty Columns']))

        console.print(table)
        
    styled_print("Validation complete.", colour="magenta")
    