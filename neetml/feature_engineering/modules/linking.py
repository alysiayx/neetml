import logging
import pprint
from math import log
from pickletools import int4
from typing import Literal
import pandas as pd
import janitor
import os
import requests
import zipfile
import io
from pathlib import Path
import cgi
from rich import print
from bs4 import BeautifulSoup

from ...utils.misc import (
    styled_print,
    load_dataframe
)

from ...utils.constants import (
    ExtRefs,
    CSP_CONFIGS,
    EXT_COL_PREFIX,
    DATA_PATHS,
    STUD_ID_COL,
    MergeMetadata,
    EXT_COL_PREFIX,
) 

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

logger = get_logger("feature_engineering")
# logger = logging.getLogger(__name__)  


def add_iod(
    input_data: pd.DataFrame,
    col_pd: str,
    iod_version: int = 2019,
    df_onspd: pd.DataFrame = None,
    df_iod: pd.DataFrame = None,
    col_onspd_pcd: str = ExtRefs.ONSPD_PCD_COL,
    col_onspd_oa: str = ExtRefs.ONSPD_OA11_COL,
    col_iod_oa: str = None,
    col_imd: str = None,
    col_iod_score_tag: str = ExtRefs.IOD_SCORE_TAG,
    prefix: str = EXT_COL_PREFIX,
) -> pd.DataFrame:
    """
    Enriches the input dataframe with deprivation and index of deprivation scores:
    - Maps postcodes to LSOA11 codes using ONSPD lookup.
    - Maps LSOA codes to IMD deciles and IoD19 scores.
    - Adds new columns for derived IMD and IoD values.
    
    *Notes*: The structure of IoD looks like this:
        Indices of Deprivation (IoD)
        │
        ├── Index of Multiple Deprivation (IMD) 
        │     ├── Income Deprivation
        │     ├── Employment Deprivation
        │     ├── Education, Skills & Training Deprivation
        │     ├── Health Deprivation and Disability
        │     ├── Crime
        │     ├── Barriers to Housing and Services
        │     └── Living Environment
        │
        ├── Income Deprivation Affecting Children Index (IDACI)
        └── Income Deprivation Affecting Older People Index (IDAOPI)

    Args:
        df: Main dataframe containing 'col_pd'.
        col_pd: Name of the postcode column in df.
        df_onspd: ONSPD lookup dataframe.
        df_iod: IoD scores dataframe.
        col_onspd: Name of the postcode column in df_onspd.
        col_lsoa: Name of the LSOA column in df_onspd and df_iod.
        col_imd: Name of the IMD decile column in df_iod.
        col_iod_score_tag: Tag for IoD score columns in df_iod.

    Returns:
        pd.DataFrame: The input dataframe with new derived columns.
    """
    
    if not col_iod_oa:
        col_iod_oa = ExtRefs.iod_oa_col(iod_version)
    
    if not col_imd:
        col_imd = ExtRefs.imd_decile_col(iod_version)
    
    if not df_onspd:
        df_onspd_bd = pd.read_csv(DATA_PATHS['EXT_DATA_DIR'] / ExtRefs.ONSPD_BD_FILE)
        df_onspd_leeds = pd.read_csv(DATA_PATHS['EXT_DATA_DIR'] / ExtRefs.ONSPD_LS_FILE)
        df_onspd = pd.concat([df_onspd_bd, df_onspd_leeds])
        logger.info(f"Loaded ONSPD lookup files for Bradford and Leeds (version {ExtRefs.ONSPD_VERSION}).")
        logger.debug(
            f"ONSPD shapes -> Bradford: {df_onspd_bd.shape}, Leeds: {df_onspd_leeds.shape}, Combined: {df_onspd.shape}"
        )
        logger.debug(f"ONSPD columns: {df_onspd.columns.tolist()}")
        styled_print(f"ONSPD lookup ready: {df_onspd.shape[0]} rows loaded", colour="green")

    if not df_iod:
        logger.info(f"Loading IoD scores from file: {ExtRefs.iod_file(iod_version)} (version {iod_version})")
        df_iod = pd.read_csv(DATA_PATHS['EXT_DATA_DIR'] / ExtRefs.iod_file(iod_version))
    
    df = input_data.copy(deep=True)
    logger.debug(f"Before mapping IoD scores, the dataframe shape: {df.shape}")
    
    # Clean and standardize postcode columns for matching
    df[f'{col_pd}_clean'] = (
        df[col_pd].str.upper().str.replace(' ', '').str.strip()
    )
    df_onspd[f'{col_onspd_pcd}_clean'] = (
        df_onspd[col_onspd_pcd].str.upper().str.replace(' ', '').str.strip()
    )
    
    # # Ensure LSOA columns are strings and stripped of whitespace
    # df[col_onspd_oa] = df[col_onspd_oa].astype(str).str.strip()
    # df_iod[col_iod_oa] = df_iod[col_iod_oa].astype(str).str.strip()

    # Map postcodes to LSOA codes
    multi = (
        df_onspd
        .groupby(f'{col_onspd_pcd}_clean')[col_onspd_oa]
        .nunique()
    )

    if (multi > 1).any():
        logger.warning("Postcode-to-LSOA is not one-to-one! But we will map postcode to first losa it appears in the ONSPD file.")
    
    postcode_to_lsoa = dict(zip(df_onspd[f'{col_onspd_pcd}_clean'], df_onspd[col_onspd_oa]))
    df[col_onspd_oa] = df[f'{col_pd}_clean'].map(postcode_to_lsoa)
    
    # Report missing LSOA mappings
    missing_lsoa = df[df[col_onspd_oa].isna()]
    if not missing_lsoa.empty:
        logger.debug(f"Missing {col_onspd_oa} for postcodes: {missing_lsoa[col_pd].unique().tolist()}")
    
    # Count how many rows have nccis_postcode as <NA> or 'ZZ99 9ZZ'
    mask_na_zz99 = df[f'{col_pd}_clean'].isna() | (df[f'{col_pd}_clean'] == 'ZZ999ZZ')
    count_na_zz99 = mask_na_zz99.sum()
    unique_persons = df.loc[mask_na_zz99, 'stud_id'].nunique()
    logger.debug(f"Number of rows with {col_pd} as <NA> or 'ZZ99 9ZZ': {count_na_zz99}")
    logger.debug(f"Number of unique persons with {col_pd} as <NA> or 'ZZ99 9ZZ': {unique_persons}")

    # Map LSOA to IMD decile
    multi = df_iod.groupby(col_iod_oa)[col_imd].nunique()

    if (multi > 1).any():
        n_multi = (multi > 1).sum()
        logger.warning(
            f"{n_multi} LSOA codes map to multiple IMD values. "
            "This indicates duplicated or inconsistent IMD data. "
            "Only the first IMD value will be used for those LSOAs."
        )
    
    # Identify IoD score and IMD decile columns and clean their names
    include_keys = {col_iod_score_tag, col_imd}
    exclude_keys = ExtRefs.IOD_EXCLUDE

    col_scores = [
        col
        for col in df_iod.columns
        if any(inc in col for inc in include_keys) 
           and not any(exc in col for exc in exclude_keys)
    ]
    
    logger.info(f"Following new features will be added into dataset: \n{"\n".join(f"- {col}" for col in col_scores)}")
    #  lsoa_to_imd = dict(
    #     zip(
    #         df_iod[col_iod_oa],
    #         df_iod[col_imd]
    #     )
    # )
    # df[f'{EXT_COL_PREFIX}_IMD'] = df[col_onspd_oa].map(lsoa_to_imd)
    
    # Map LSOA11 to each IoD score and add as new columns
    for col in col_scores:
        if col in ExtRefs.IMD_RENAME_MAP:
            new_colname = ExtRefs.IMD_RENAME_MAP[col]
        else:
            new_colname = janitor.clean_names(
                pd.DataFrame(columns=[col]),
                strip_underscores=True
            ).columns.tolist()[0]
        
        new_colname = f'{prefix}_{new_colname}'
        
        logger.debug(f"Renaming column '{col}' to '{new_colname}' for better readability.")
        lsoa_to_score = dict(zip(df_iod[col_iod_oa], df_iod[col]))
        df[new_colname] = df[col_onspd_oa].map(lsoa_to_score)
        
        # missing_score = df[df[new_colname].isna()]
        # if not missing_score.empty:
        #     logger.debug(f"Missing '{col}' for {missing_score.shape[0]} rows with postcodes: {missing_score[col_pd].unique().tolist()}")
        # print('\n')
    
    # Drop temporary columns
    df.drop(columns=[f'{col_pd}_clean', ExtRefs.ONSPD_OA11_COL, ExtRefs.ONSPD_OA21_COL], inplace=True, errors="ignore")
    
    logger.debug(f"After mapping IoD scores, the dataframe shape: {df.shape}")
    
    added_cols = set(df.columns) - set(input_data.columns)
    format_added_cols = pprint.pformat(added_cols, indent=4, compact=True)
    logger.info(f"Added {len(added_cols)} IoD features: \n{format_added_cols}")

    return df

def _get_available_datatypes(la_code: str, academic_year: str) -> list[str]:
    """
    Hit the region-selection page for that LA & year, parse out
    every <input name="datatypes" value="..."> and return the list of values.
    """
    params = {
        "currentstep":  "region",
        "regiontype":   "la",
        "la":           la_code,
        "downloadYear": academic_year
    }
    # fetch the HTML page (no downloads yet)
    try:
        resp = requests.get(CSP_CONFIGS["BASE_URL"], params=params, headers=CSP_CONFIGS["HEADERS"])
        resp.raise_for_status()
    except requests.HTTPError as e:
        logger.warning(f"Cannot find any data type for LA={la_code}, year={academic_year}: {e}")
        return None
    
    soup = BeautifulSoup(resp.text, "html.parser")

    # find all inputs named "datatypes" (these are the checkboxes)
    inputs = soup.find_all("input", attrs={"name": "datatypes", "value": True})
    values = [i["value"] for i in inputs]
    
    return values

def fetch_school_perf_data(
    la_code: int | str,
    academic_start_year: int,
    academic_end_year: int,
    data_types: list[str] | str = None,
    file_format: str = "xlsx",
    out_root: str = Path(CSP_CONFIGS["DEFAULT_OUT_DIR"]),
) -> str:
    """
    Downloads and extracts school performance data for a specified local authority and academic year.

    Args:
        la_code (int or str): Local authority code.
        academic_start_year (int): academic start year.
        academic_end_year (int): academic end year.
        data_types (list[str] or str, optional): List of data type identifiers to filter the download.
                                          If None, fetches available types in all valid data types.
                                          If 'all', use all valid data types.
        file_format (str, optional): 'csv' or 'xlsx'. Default is 'xlsx'.
        out_root (str, optional): Root directory to save extracted files. Default from CSP_CONFIGS.
        
    Returns:
        str: Path to the directory containing the extracted files.

    """
    
    logger.info("Start downloading school performance data")
    
    la_code = str(la_code)
    out_root = Path(out_root) / CSP_CONFIGS["FOLDER_NAME"]
    
    for year in range(academic_start_year, academic_end_year):
        academic_year = f"{year}-{year+1}"

        # Define effective parameters
        valid_data_types = _get_available_datatypes(la_code, academic_year)
        
        if data_types is None:
            data_types = CSP_CONFIGS['DEFAULT_DATA_TYPES']
            year_data_types = [dt for dt in valid_data_types if any(kw.lower() in dt.lower() for kw in data_types)]
        elif data_types == 'all':
            year_data_types = valid_data_types
        else:
            if data_types is not None:
                year_data_types = [dt for dt in valid_data_types if any(kw.lower() in dt.lower() for kw in data_types)]
            else:
                year_data_types = None
        
        out_dir = out_root / f"LA_{la_code}_{academic_year}"

        # Return early if already downloaded
        if out_dir.exists():
            logger.info(f"Skipping download: {out_dir} already exists.")
            continue
        
        if not year_data_types: # year_data_types is None or [] (empty list)
            logger.info(f"Skipping download: {out_dir} as no valid data types found.")
            print(f"Available data types for LA={la_code}, year={academic_year}: {valid_data_types}")
            continue
        else:
            logger.info(f"Following data types will be downloaded: {year_data_types} for LA={la_code}, year={academic_year}")
        
        # Build request params
        params = {
            "currentstep": "datatypes",
            "regiontype": "la",
            "la": la_code,
            "downloadYear": academic_year,
            "datatypes": year_data_types,
        }

        session = requests.Session()
        try:
            resp = session.get(
                CSP_CONFIGS["BASE_URL"],
                params=params,
                headers=CSP_CONFIGS["HEADERS"]
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            logger.warning(f"Failed to load selection page for LA={la_code}, year={academic_year}: {e}")
            continue

        # Extract download link
        soup = BeautifulSoup(resp.text, "html.parser")
        link_text = "Data in CSV format" if file_format == "csv" else "Data in XLS format"
        link_tag = soup.find("a", string=link_text)

        if not link_tag or not link_tag.get("href"):
            raise RuntimeError(f"Download link '{link_text}' not found for LA={la_code}, year={academic_year}.")

        download_url = link_tag["href"]
        if not download_url.startswith("http"):
            download_url = f"https://www.compare-school-performance.service.gov.uk{download_url}"

        # Download ZIP
        try:
            zi_resp = session.get(download_url, headers=CSP_CONFIGS["HEADERS"])
            zi_resp.raise_for_status()
            # print(download_url)
        except requests.HTTPError as e:
            logger.warning(f"Download failed for LA={la_code}, year={academic_year}: {e}")
            continue
        
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_buffer = io.BytesIO(zi_resp.content)
        
        # Get filename from Content-Disposition header if available
        cd = zi_resp.headers.get("Content-Disposition")
        if cd:
            _, params = cgi.parse_header(cd)
            filename = params.get("filename")
            styled_print(f"Found following file(s) can be downloaded: {filename}")
   
        # Check if the response is a valid zip archive
        if filename.endswith(".zip"):
            with zipfile.ZipFile(zip_buffer) as archive:
                file_list = archive.namelist()
                out_dir.mkdir(parents=True, exist_ok=True)
                for member in file_list:
                    if member.endswith("/"):
                        continue
                    filename = os.path.basename(member)
                    with archive.open(member) as src, open(out_dir / filename, "wb") as dst:
                        dst.write(src.read())
                logger.info(f"Downloaded and extracted ZIP into: {out_dir}")
        else:
            # Save raw content as a single file
            out_file = out_dir / filename.replace('/', '_')
            with open(out_file, "wb") as f:
                f.write(zi_resp.content)
            logger.info(f"Downloaded & extracted files to: {out_dir}")
        
    return None

def build_school_perf_data(
    school_perf_dir: str | Path = Path(CSP_CONFIGS["DEFAULT_OUT_DIR"]) / CSP_CONFIGS["FOLDER_NAME"],
    source_mapping: dict = ExtRefs.SCHOOL_SRC_MAPPING,
    join_keys: tuple = ExtRefs.SCHOOL_JOIN_KEYS,
    save_name: str = ExtRefs.SCHOOL_SAVE_NAME,
) -> pd.DataFrame:
    school_perf_dir = Path(school_perf_dir)
    
    logger.info(f"Looking for school performance data files in: {school_perf_dir}")
    
    final_out_path = school_perf_dir / save_name
    
    if final_out_path.exists():
        logger.info(f"Final merged file already exists at: {final_out_path}. Skipping merging process.")
        return load_dataframe(final_out_path)
    
    if isinstance(join_keys, str):
        join_keys = (join_keys,)
    
    dfs_to_merge = []
    join_keys_renamed = [ExtRefs.SCHOOL_BASIC_SCHEMA.get(k, {}).get("name", k) for k in join_keys]
    
    for folder in sorted([p for p in school_perf_dir.iterdir() if p.is_dir()]):
        dfs = []
        
        logger.debug(f"Processing folder: {folder.name}")
        out_path = school_perf_dir / f"{folder.name}.xlsx"
        
        if out_path.exists():
            logger.info(f"Skipping merging for {folder.name} as output file already exists: {out_path}")
            dfs_to_merge.append(pd.read_excel(out_path))
            continue
        
        for file in folder.iterdir():
            
            if not file.is_file() or file.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                continue

            file_key = file.stem.lower()
            if file_key not in source_mapping:
                continue
            
            logger.debug(f"Found file: {file.name}")
            
            rename_map = source_mapping[file_key]
            
            if all(k not in [v["name"] for v in rename_map.values()] for k in join_keys_renamed):
                logger.warning(f"Join keys {join_keys} (renamed as {join_keys_renamed}) not found in rename map for file: {file.name}. The join keys are set as {join_keys}, but the columns in the dataframes are {rename_map.values()}. Please check the source mapping and the files.")
            
            usecols = set(list(join_keys) + list(rename_map.keys()))

            header = pd.read_csv(file, nrows=0) if file.suffix == ".csv" else pd.read_excel(file, nrows=0)
            valid_usecols = header.columns.intersection(usecols).tolist()
            skips_rows = 0
            
            if len(valid_usecols) == 0:
                header = pd.read_csv(file, nrows=0, skiprows=1) if file.suffix == ".csv" else pd.read_excel(file, nrows=0, skiprows=1)
                valid_usecols = header.columns.intersection(usecols).tolist()
                skips_rows = 1
            
            valid_usecols_fmt = pprint.pformat(valid_usecols, indent=4, compact=True)
            logger.debug(f"Found valid columns in file {file.name}: \n{valid_usecols_fmt}")
            
            df = pd.read_csv(file, usecols=valid_usecols, skiprows=skips_rows) if file.suffix == ".csv" else pd.read_excel(file, usecols=valid_usecols, skiprows=skips_rows)
            
            if df.empty:
                logger.warning(f"No valid data found in file: {file.name}. Skipping this file.")
                continue
            
            # NON_NUMERIC_MARKERS = ["NP", "SUPP", "LOWCOV"]
            # df.replace(NON_NUMERIC_MARKERS, pd.NA, inplace=True)
                
            # change dtypes according to mapping
            for col, spec in rename_map.items():
                if col in df.columns:
                    
                    dtype = spec.get("dtype")
                    new_name = spec.get("name", col)
                    
                    # remove the '%' sign and multiply by 100 if the column is expected to be a percentage but contains values in range 0-1, or contains '%' sign in string format
                    # we keep all values in range 0-100 for percentage columns
                    s = df[col].astype(str)
                    if s.str.contains("%", regex=True).any() or new_name.lower().endswith("pct"):
                        logger.warning(f"Converting percentage string to numeric in column: {col} in file: {file.name}, please double check if this is expected. The conversion will remove the '%' sign.")
                        logger.debug(f"Sample values before conversion: {s.head(10).tolist()}")
                        df[col] = pd.to_numeric(s.str.rstrip("%"), errors="coerce")
                        logger.debug(f"Sample values after conversion: {df[col].head(10).tolist()}")
                        
                    if new_name.lower().endswith("pct") and df[col].dropna().apply(lambda x: 0 <= x <= 1).all():
                        logger.warning(f"Column '{col}' ({new_name}) in file: {file.name} seems to be a percentage column with values between 0 and 1 after conversion. Please double check if this is expected. If this column is expected to be a percentage, the values will be multiplied by 100.")
                        logger.debug(f"Sample values before conversion: {df[col].head(10).tolist()}")
                        df[col] = (df[col] * 100).round(2)
                        logger.debug(f"Sample values after conversion: {df[col].head(10).tolist()}")
                 
                    #  we keep all values in range 0-1 for rate columns
                    if new_name.lower().endswith("rate") and max(df[col].dropna()) > 1:
                        logger.warning(f"Column '{col}' ({new_name}) in file: {file.name} seems to be a rate column with values greater than 1 after conversion. Please double check if this is expected. If this column is expected to be a rate, the values will be divided by 100.")
                        logger.debug(f"Sample values before conversion: {df[col].head(10).tolist()}")
                        df[col] = (df[col] / 100).round(2)
                        logger.debug(f"Sample values after conversion: {df[col].head(10).tolist()}")
                        
                    # then convert to the specified dtype, if any
                    if dtype:
                        try:
                            df[col] = df[col].astype(dtype)
                            logger.debug(f"Converted column '{col}' to dtype '{dtype}' in file: {file.name}")
                        except Exception as e:
                            logger.warning(f"Failed to convert column '{col}' to dtype '{dtype}' in file: {file.name}: {e}")
                            try:
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                                logger.debug(f"Coerced column '{col}' to numeric in file: {file.name}")
                            except Exception as e:
                                logger.warning(f"Failed to coerce column '{col}' to numeric in file: {file.name}: {e}")

                        if dtype == 'string':
                            df[col] = df[col].str.strip().str.replace(r"\.0$", "", regex=True)
            
            # rename columns according to mapping
            df.rename(columns={col: spec["name"] for col, spec in rename_map.items()}, inplace=True)
            
            if "ofsted_rating" in df.columns:
                ofsted_map = {
                    1: "Outstanding",
                    2: "Good",
                    3: "Requires improvement",
                    4: "Inadequate",
                }

                df["ofsted_rating"] = df["ofsted_rating"].map(ofsted_map)

            dfs.append(df)
            
        if not dfs:
            continue

        merged = dfs[0]
        for df_next in dfs[1:]:
            common_keys = [k for k in join_keys_renamed if k in merged.columns and k in df_next.columns]
            
            if not common_keys:
                raise ValueError(f"No common join keys found when merging files in folder: {folder.name}. The join keys are set as {join_keys_renamed}, but the columns in the dataframes are {merged.columns.tolist()} and {df_next.columns.tolist()}. Please check the source mapping and the files.")

            logger.debug(f"before merge: {merged.shape}, {df_next.shape}")
            
            # common keys should be numeric
            merged[common_keys] = merged[common_keys].apply(pd.to_numeric, errors="coerce")
            df_next[common_keys] = df_next[common_keys].apply(pd.to_numeric, errors="coerce")
            
            merged = merged.merge(df_next, on=common_keys, how="outer", suffixes=("", "_dup"))
            
            merged.dropna(subset=common_keys, how="all", inplace=True)
                        
            dup_cols = [c for c in merged.columns if c.endswith("_dup")]

            for c in dup_cols:
                base_col = c[:-4] 
                if base_col in merged.columns:
                    merged[base_col] = merged[base_col].combine_first(merged[c])

            merged.drop(columns=dup_cols, inplace=True)
            
            logger.debug(f"after merge: {merged.shape}")
            
            assert merged.columns.duplicated().sum() == 0, f"Duplicated columns found in merged dataframe after merging files in folder: {folder.name}. Please check the source mapping and the files. The number of duplicated common keys is {merged[common_keys].duplicated().sum()}, all columns in dataframe {merged.columns.tolist()}."
            assert df_next.columns.duplicated().sum() == 0, f"Duplicated columns found in the next dataframe when merging files in folder: {folder.name}. Please check the source mapping and the files. The number of duplicated common keys is {df_next[common_keys].duplicated().sum()}, all columns in dataframe {df_next.columns.tolist()}."
        
        # add recorded year (academic year end) column based on folder name, which is in format "LA_{la_code}_{academic_year}"
        merged[ExtRefs.SCHOOL_YEAR_COL] = folder.name.split("-")[-1]
        
        # final check all percentage columns are between 0 and 100, and rate columns are between 0 and 1, if not, log a warning
        for col in merged.columns:
            if col.lower().endswith("pct") and not merged[col].dropna().apply(lambda x: 0 <= x <= 100).all():
                raise ValueError(f"Column '{col}' contains values outside the expected range in file: {file.name}. Please check if this column is expected to be a percentage or rate and if the values are correct. Sample values: {merged[col].dropna().unique()[:10].tolist()}")
            if col.lower().endswith("rate") and not merged[col].dropna().apply(lambda x: 0 <= x <= 1).all():
                raise ValueError(f"Column '{col}' contains values outside the expected range in file: {file.name}. Please check if this column is expected to be a percentage or rate and if the values are correct. Sample values: {merged[col].dropna().unique()[:10].tolist()}")
        
        merged.drop_duplicates(inplace=True)
        
        dfs_to_merge.append(merged)
        
        merged.to_excel(out_path, index=False)
        
        logger.info(f"Created school performance data file: {out_path}")
        
    df_final = pd.concat(dfs_to_merge, ignore_index=True)
    
    df_final.drop_duplicates(inplace=True)
    
    df_final.to_parquet(final_out_path, index=False)
    logger.info(f"Created final merged school performance data file: {final_out_path}")
    
    return df_final

def link_school_perf_data(
    input_data: pd.DataFrame,
    school_data: pd.DataFrame,
    left_on: str | list | None = None,
    right_on: str | list | None = None,
    prefix: str = EXT_COL_PREFIX,
    lag_suffix: str = None,
) -> pd.DataFrame:
    """
    Links the main dataframe with school performance data based on school code and recorded year.

    Args:
        input_data (pd.DataFrame): Main dataframe containing student records.
        school_data (pd.DataFrame): Dataframe containing school performance data.
        left_on (str or list): Column name or list of column names to join on in the input dataframe.
        right_on (str or list): Column name or list of column names to join on in the school performance dataframe.
        prefix (str): Prefix to add to the linked school performance columns to avoid name clashes.
        lag_suffix (str): Suffix to add to the linked school performance columns to indicate the lag applied to the year column, if any.

    Returns:
        pd.DataFrame: The input dataframe enriched with school performance data.
    """
    
    if isinstance(left_on, str):
        left_on = [left_on]
    if isinstance(right_on, str):
        right_on = [right_on]
    
    df = input_data.copy(deep=True)
    df_school = school_data.copy(deep=True)
    n_rows = df.shape[0]
    
    prefix = prefix if prefix and prefix.endswith("_") else f"{prefix}_" if prefix else ""
    lag_suffix = lag_suffix if lag_suffix and lag_suffix.startswith("_") else f"_{lag_suffix}" if lag_suffix else ""
    
    school_cols = [col for col in df_school.columns if col not in right_on]
    df_school.rename(columns={col: f"{prefix}{col}{lag_suffix}" for col in school_cols}, inplace=True)
    
    logger.debug(f"Before merge, the dataframe shape: {df.shape}")
    logger.debug(f"Before merge, the school dataframe shape: {df_school.shape}")
    
    # Merge on join keys and year
    merged_df = df.merge(
        df_school,
        left_on=[
            df[col].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
            for col in left_on
        ],
        right_on=[
            df_school[col].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
            for col in right_on
        ],
        how='left',
        suffixes=("", "_school")
    )
    
    # merged_df = merged_df.drop(columns=right_on)
    
    # find all-null columns and drop them
    non_cols = merged_df.columns[merged_df.isna().all()].tolist()
    non_cols_fmt = pprint.pformat(sorted(non_cols), indent=4, compact=True)
    if non_cols:
        logger.warning(f"Dropping columns with all null values : {non_cols_fmt}.")
    
    merged_df.dropna(axis=1, how='all', inplace=True)
    
    assert merged_df.shape[0] == n_rows, f"Number of rows changed after merge! Before: {n_rows}, after: {merged_df.shape[0]}. Please check the join keys and the school performance data. The join keys are set as {left_on} and {right_on}, but the columns in the school performance dataframe are {df_school.columns.tolist()}."
    
    # remove join keys
    new_cols = set(merged_df.columns) - set(df.columns)
    new_valid_cols = [col for col in new_cols if col in df_school.columns and col not in right_on]
    merged_df = merged_df.drop(columns=[col for col in new_cols if col not in new_valid_cols])
    
    logger.debug(f"After merge, merged dataframe shape: {merged_df.shape}")
    
    formatted_cols = pprint.pformat(sorted(new_valid_cols), indent=4, compact=True)
    logger.info(f'Linked columns ({len(new_valid_cols)}):\n{formatted_cols}')

    logger.info(f"Completed linking. Merged dataframe shape: {merged_df.shape}")
    
    return merged_df
