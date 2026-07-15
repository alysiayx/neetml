# NEETML

![Python 3.11 and 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)
[![PyPI version](https://img.shields.io/pypi/v/neetml.svg)](https://pypi.org/project/neetml/)
![Release status: pre-release](https://img.shields.io/badge/status-pre--release-orange)
[![License](https://img.shields.io/github/license/alysiayx/neetml.svg?cacheSeconds=60)](https://github.com/alysiayx/neetml/blob/main/LICENSE)

NEETML is a machine learning toolkit for identifying young people at risk of becoming **Not in Education, Employment or Training (NEET)** in England.

> **Pre-release notice**
>
> The current package is intended for testing. Its interfaces and default data
> schemas may change before the first stable release.

## Contents

- [NEETML](#neetml)
  - [Contents](#contents)
  - [Installation](#installation)
  - [Key features](#key-features)
  - [Current version support](#current-version-support)
  - [About the project](#about-the-project)
    - [Project partner](#project-partner)
    - [Background research](#background-research)
  - [Data coverage](#data-coverage)
  - [Potential risk of NEET indicators](#potential-risk-of-neet-indicators)
  - [Similar tools](#similar-tools)
  - [Citation](#citation)

## Installation

Install NEETML from PyPI:

```bash
python -m pip install neetml
```

## Key features

The project aims to:

- Predict the risk of young people becoming NEET
- Provide analysis at council, school and individual levels
- Support early intervention by education teams and local authorities
- Include tools for data preparation, predictive modelling and visualisation
- Help users explore key risk factors associated with educational disengagement

> **Scope clarification:** The list above describes the direction of the
> project. The checklist below is the source of truth for functionality included
> in the current package.

## Current version support

- [x] Data inspection, metadata extraction and validation
- [x] Filename and column-name standardisation
- [x] Data cleaning, profiling, merging and aggregation
- [x] School performance and deprivation data linkage
- [x] Demographic, language and school feature engineering
- [ ] Model training and evaluation
- [ ] NEET risk scoring and prediction
- [ ] Model explainability and risk-factor reporting
- [ ] User-facing visualisations and dashboards

## About the project

NEETML was developed to help local authorities in England identify young people aged 16 to 18 who may be at risk of becoming NEET.

> **Project history:** NEETML is a comprehensive update and expansion of
> [DSSGxUK/s23_neet](https://github.com/DSSGxUK/s23_neet), extending the
> original framework with a focus on a more robust and user-friendly workflow.

The project uses predictive modelling to support analysis at council, school and individual levels. Its purpose is to help local authorities, education providers and support teams identify potential risks earlier and make more informed decisions about targeted interventions.

Through the timely implementation of tailored interventions using intelligence provided by the project, we sought to empower the lives of the young people by ensuring they stayed engaged in education, training or found gainful employment opportunities, rather than become NEET.

### Project partner

The project worked in collaboration with the following partners:

- City of Bradford Metropolitan District Council (NIHR Health Determinants Metropolitan Collaboration)

### Background research

<details>

<summary><strong>Read the background research summary</strong></summary>

The transition from adolescence to adulthood is a critical phase that shapes an individual’s future prospects, impacting their education, employment, and overall well-being. Among the challenges that young people face during this transition is the risk of being categorized as ”NEET” – Not in Education, Employment, or Training. The NEET status has garnered significant attention due to its association with adverse outcomes, particularly in terms of mental health and social exclusion. The term ”NEET” emerged in the late 1990s, in the United Kingdom, and has been used to capture disengagement and social exclusion among young adults up to the age of 35 in some countries.

The phenomenon of being NEET is multifaceted and influenced by various factors encompassing individual characteristics, family background, socioeconomic status, educational achievements, aspirations, mental health, and environmental conditions. As a result, numerous studies have sought to dissect the complex interplay of these factors and shed light on the predictors of NEET status. Here we review and synthesise a range of studies that explore the determinants and consequences of being NEET.

The literature surrounding NEET status and its correlations present a mosaic of findings that underscore the intricate relationship between various factors and the likelihood of becoming NEET. Studies have illuminated the role of family socioeconomic status, parental education, and household income as influential factors. For instance, parental socioeconomic resources, including low education, unemployment, and economic adversity, have been linked to an increased risk of NEET status. Additionally, adverse childhood experiences, such as abuse, neglect, parental substance use, and witnessing domestic violence, have been identified as predictors of NEET status, though their influence is somewhat modest when accounting for socioeconomic status. Educational attainment emerges as a powerful predictor, with cognitive abilities and aspirations playing vital roles. Cognitive abilities, as measured by key stage test scores, have shown consistent associations with the risk of becoming NEET. Aspirations, both of parents and young individuals, hold considerable sway, influencing the transition from education to employment. Moreover, health status, particularly mental health, has garnered increased attention as a determinant of NEET status. Recent trends indicate a rising correlation between self-reported mental ill health and NEET status, with mental health having the largest effect on the probability of being NEET, especially among males.

The impact of environmental factors cannot be underestimated, as evidenced by the variation in NEET rates across different regions and local labor market conditions. Early leaving from education, referred to as ”EL,” has emerged as a related concept, demonstrating the need to differentiate between education-related disengagement and broader social exclusion. The complex interplay of these factors highlights the need for comprehensive and multifaceted interventions to address the NEET phenomenon effectively.

To sum up, the landscape of NEET research reveals a nuanced web of influences that shape the transition from education to employment for young people. Individual characteristics, family background, educational achievements, mental health, and environmental conditions collectively contribute to the risk of being NEET. Understanding these determinants and their intricate connections is essential for formulating targeted policies and interventions that can effectively address the challenges faced by NEET individuals. As the research continues to evolve, there is a growing recognition of the need to consider both cognitive and non-cognitive factors, socioeconomic resources, aspirations, and mental health in designing strategies that support young people’s successful transition into adulthood.
</details>

## Data coverage

| Data source | Information used by the project |
| --- | --- |
| National Client Caseload Information System (NCCIS) | Local authorities submit NCCIS data to the Department for Education (DfE). It records participation in education and training and provides the prediction target through activity codes. |
| School Census | Student demographic information, including gender, ethnicity, age, language, Free School Meals (FSM) eligibility and Special Educational Needs (SEN). |
| Key Stage 4 (KS4) | Student grades and attainment scores. |
| Attendance | Termly sessions, absences and reasons for absence, including exclusions and late entries. |
| Exclusions | A student's historical exclusion status. |
| School-level data | School performance data for England, filtered at local-authority level. Postcodes support school-to-home distance features, while Ofsted ratings help describe relative school performance. Source: [Compare school and college performance](https://www.find-school-performance-data.service.gov.uk/download-data). |
| Socio-economic factors | English Indices of Deprivation data, including the Income Deprivation Affecting Children Index (IDACI) and related scores used to group residential areas by deprivation. Source: [English indices of deprivation 2019](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019). |

> **Data note:** Source availability, permitted use and local schemas may vary
> between local authorities. Users are responsible for validating their input
> data before analysis.

## Potential risk of NEET indicators

Our work concluded the following were the most prevalent RONIs using the range of datasets incorporated within the modelling undertaken:

- GCSE Attainment
- Absences
- Support Level
- Free School Meals
- Special Education Needs
- IDACI score of the living area
- School-to-home distance

## Similar tools

NEET tool developed by [Insight Bristol](https://www.bristol.gov.uk/residents/social-care-and-health/children-and-families/insight-bristol) and used within the [Think Family Database](https://thinkfamily.bristolsafeguarding.org/think-family/?query=NEET).

## Citation

If you use **neetml** in your research, please cite this repository using the GitHub citation information or the BibTeX entry available under **"Cite this repository"**.