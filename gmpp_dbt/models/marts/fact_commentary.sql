{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['project_id']) }} as project_key,
    {{ dbt_utils.generate_surrogate_key(['report_year']) }} as date_key,
    project_description,
    departmental_commentary,
    schedule_narrative,
    in_year_variance_narrative,
    costs_narrative
from {{ ref('int_gmpp_unioned') }}
WHERE project_id is not null