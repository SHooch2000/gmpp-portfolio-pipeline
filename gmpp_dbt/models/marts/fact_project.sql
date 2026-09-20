{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['f.project_id']) }} as project_key,
    {{ dbt_utils.generate_surrogate_key(['f.department']) }} as department_key,
    {{ dbt_utils.generate_surrogate_key(['f.report_year']) }} as date_key,
    f.dca_rating,
    f.baseline_cost,
    f.forecast_cost,
    f.cost_variance_pct,
    f.whole_life_cost,
    f.start_date,
    f.end_date,
    f.report_year
from {{ ref('int_gmpp_unioned') }} f
where f.project_id is not null