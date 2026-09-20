{{ config(materialized='table') }}

select {{ dbt_utils.generate_surrogate_key(['project_id']) }} as project_key,
       coalesce(project_id, 'UNKNOWN') as project_id,
       max(project_name) as project_name,
       max(annual_report_category) as annual_report_category
from {{ ref('int_gmpp_unioned') }}
group by project_id