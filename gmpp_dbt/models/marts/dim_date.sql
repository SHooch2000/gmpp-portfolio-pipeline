{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['report_year']) }} as date_key,
    max(report_year) as report_year
from {{ ref('int_gmpp_unioned') }}

group by report_year