<h1> NEETML</h1>

**NEETML is an open-source machine learning and data visualisation tool for predicting which young people are at risk of becoming NEET — Not in Education, Employment or Training — in England.**

## Key features

- Predicts the risk of young people becoming NEET
- Provides analysis at council, school and individual levels
- Supports early intervention by education teams and local authorities
- Includes tools for data preparation, predictive modelling and visualisation
- Helps users explore key risk factors associated with educational disengagement

> **Note:** This project is a comprehensive update and expansion of the previous project [DSSGxUK/s23_neet](https://github.com/DSSGxUK/s23_neet). It introduces significant enhancements and new features that improve upon the original framework, designed to offer a more robust and user-friendly experience.

## About the Project

NEETML was developed to help local authorities in England identify young people aged 16 to 18 who may be at risk of becoming NEET.

The project uses predictive modelling to support analysis at council, school and individual levels. Its purpose is to help local authorities, education providers and support teams identify potential risks earlier and make more informed decisions about targeted interventions.

Through the timely implementation of tailored interventions using intelligence provided by the project, we sought to empower the lives of the young people by ensuring they stayed engaged in education, training or found gainful employment opportunities, rather than become NEET.

- [Project Partners](#project-partners)
- [Background research summary on the implications of becoming NEET](#background-research-summary-on-the-implications-of-becoming-neet)
- [How to Use the Tool](#how-to-use-the-tool)
  - [Clone the GitHub Repository](#clone-the-github-repository)
  - [Installing from GitHub](#installing-from-github)
    - [Install Pre-requisite Python Packages](#install-pre-requisite-python-packages)
- [Data Description](#data-description)
  - [NCCIS Data](#nccis-data)
  - [School Census Data](#school-census-data)
  - [KS4 Data](#ks4-data)
  - [Attendance Data](#attendance-data)
  - [Exclusions Data](#exclusions-data)
  - [School Level Data](#school-level-data)
  - [Socio-Economic Factors](#socio-economic-factors)
- [Potential Risk Of NEET Indicators (RONI)](#potential-risk-of-neet-indicators-roni)
  - [File Descriptions](#file-descriptions)
- [Similar Tools](#similar-tools)

## Project Partners

The project worked in collaboration with the following partners:

- City of Bradford Metropolitan District Council (NIHR Health Determinants Metropolitan Collaboration)
  
## Background research summary on the implications of becoming NEET

<details>
The transition from adolescence to adulthood is a critical phase that shapes an individual’s future prospects, impacting their education, employment, and overall well-being. Among the challenges that young people face during this transition is the risk of being categorized as ”NEET” – Not in Education, Employment, or Training. The NEET status has garnered significant attention due to its association with adverse outcomes, particularly in terms of mental health and social exclusion. The term ”NEET” emerged in the late 1990s, in the United Kingdom, and has been used to capture disengagement and social exclusion among young adults up to the age of 35 in some countries.

The phenomenon of being NEET is multifaceted and influenced by various factors encompassing individual characteristics, family background, socioeconomic status, educational achievements, aspirations, mental health, and environmental conditions. As a result, numerous studies have sought to dissect the complex interplay of these factors and shed light on the predictors of NEET status. Here we review and synthesise a range of studies that explore the determinants and consequences of being NEET.

The literature surrounding NEET status and its correlations present a mosaic of findings that underscore the intricate relationship between various factors and the likelihood of becoming NEET. Studies have illuminated the role of family socioeconomic status, parental education, and household income as influential factors. For instance, parental socioeconomic resources, including low education, unemployment, and economic adversity, have been linked to an increased risk of NEET status. Additionally, adverse childhood experiences, such as abuse, neglect, parental substance use, and witnessing domestic violence, have been identified as predictors of NEET status, though their influence is somewhat modest when accounting for socioeconomic status. Educational attainment emerges as a powerful predictor, with cognitive abilities and aspirations playing vital roles. Cognitive abilities, as measured by key stage test scores, have shown consistent associations with the risk of becoming NEET. Aspirations, both of parents and young individuals, hold considerable sway, influencing the transition from education to employment. Moreover, health status, particularly mental health, has garnered increased attention as a determinant of NEET status. Recent trends indicate a rising correlation between self-reported mental ill health and NEET status, with mental health having the largest effect on the probability of being NEET, especially among males.

The impact of environmental factors cannot be underestimated, as evidenced by the variation in NEET rates across different regions and local labor market conditions. Early leaving from education, referred to as ”EL,” has emerged as a related concept, demonstrating the need to differentiate between education-related disengagement and broader social exclusion. The complex interplay of these factors highlights the need for comprehensive and multifaceted interventions to address the NEET phenomenon effectively.

To sum up, the landscape of NEET research reveals a nuanced web of influences that shape the transition from education to employment for young people. Individual characteristics, family background, educational achievements, mental health, and environmental conditions collectively contribute to the risk of being NEET. Understanding these determinants and their intricate connections is essential for formulating targeted policies and interventions that can effectively address the challenges faced by NEET individuals. As the research continues to evolve, there is a growing recognition of the need to consider both cognitive and non-cognitive factors, socioeconomic resources, aspirations, and mental health in designing strategies that support young people’s successful transition into adulthood.
</details>

## How to Use the Tool

This section provides instructions on how to use the tool either by running a pre-built executable or by installing it from GitHub and using Streamlit to run it.

### Clone the GitHub Repository

```bash
git clone https://github.com/alysiayx/neetml.git
cd neetml
```
### Installing from GitHub

If you prefer to install from GitHub, follow these steps:

#### Install Pre-requisite Python Packages

**Option 1: Using Poetry**
Type the following command in your terminal:

```bash
    pip install poetry
    poetry install
    poetry shell # activate the virtual environment created by poetry
```

A virtual environment for this project will be created after this step. Poetry generates the virtual environments based on the project's directory name and the versions of Python available (e.g., `neetml-py3.11`). You can list and verify the environment with `poetry env list`.

**Option 2: Using Conda**
You can change the `prefix` variable in `environment.yml` to the directory where you want the conda environment to be located. For example:

```bash
    prefix="/path/to/neet_ml_env"
```

Then type the following command in your terminal:

```bash
    # create a conda environment called "neet_ml_env" using
    # the specifications provided in "environment.yml"
    conda env create -f environment.yml 
    # activate this virtual environment
    conda activate neet_ml_env 
```

A virtual environment called `neet_ml_env` will be created after this step.

**Option 3: Using Setuptools**
Modify the `pyproject.toml` first:

```bash
  [build-system]
  requires = ["poetry-core", "setuptools", "wheel"]
  # build-backend = "poetry.core.masonry.api" # Using Poetry
  build-backend = "setuptools.build_meta" # Using Setuptools
```

Type the following command in your terminal:

```bash
   chmod +x setup_environment.sh # make sure this script executable in Unix-like system
   ./setup_environment.sh # run the setup script
```

A virtual environment called `neet_ml_env` will be created after this step.

## Data Description

### NCCIS Data

National Client Caseload Information System (NCCIS) data is submitted to the Department for Education(DfE) by the local authorities. It monitors and records the extent to which the individual is involved with education and training. It is the file which contains the target variable for our prediction model (through the activity codes).

### School Census Data

This data provides demographic information about students such as gender, ethnicity, age, language, eligibility for Free School Meals (FSMs) or Special Educational Needs (SENs).

### KS4 Data

It holds information related to the student's grades and various attainment scores.

### Attendance Data

This data captures the attendance of students along with features as termly sessions, absences, and reasons for absences, e.g. exclusions, late entries etc.

### Exclusions Data

This data captures the information about an individual’s historical exclusion status.

### School Level Data

The data is obtained from https://www.find-school-performance-data.service.gov.uk/download-data. The school performance dataset contains data for all schools in England, and it was filtered at the local authority level. The data includes information about the school postcode, which was used during feature engineering to calculate the distance from the individual’s place of living to the school where they study. In addition to this, the categorisation of schools based on the Ofsted ratings helped distinguish the relative performance of the school.

### Socio-Economic Factors

The dataset is called the English Indices of Deprivation and is obtained from https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019. It is recorded every four years - the latest is for the year 2019. It provides information about Income Deprivation Affecting Children Index (IDACI) and other scores, which help to categorise the living area of an individual according to various bands of deprivation.

## Potential Risk Of NEET Indicators (RONI)

Our work concluded the following were the most prevalent RONIs using the range of datasets incorporated within the modelling undertaken:

- GCSE Attainment
- Absences
- Support Level
- Free School Meals
- Special Education Needs
- IDACI score of the living area
- School-to-home distance

### File Descriptions

- **`environment.yml`**
  - This Conda environment file is used to create a development environment with all necessary dependencies. Run `conda env create -f environment.yml` to set up the environment.

- **`poetry.lock`**
  - This file ensures that the same versions of all dependencies are used whenever you or someone else installs them using Poetry. It provides consistency across installations.

- **`pyproject.toml`**
  - Used by Poetry for dependency management and project settings. It includes dependencies, package configuration, and other metadata that helps manage the project.

- **`setup_environment.sh`**
  - A shell script to set up the project environment. It might install necessary packages, set environment variables, or perform other setup tasks. Execute this script to configure the project environment on a new machine.

</details>

## Similar Tools

NEET tool developed by [Insight Bristol](https://www.bristol.gov.uk/residents/social-care-and-health/children-and-families/insight-bristol) and used within the [Think Family Database](https://thinkfamily.bristolsafeguarding.org/think-family/?query=NEET).
