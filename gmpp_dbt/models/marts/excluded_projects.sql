-- models/marts/excluded_projects.sql — a small audit table, cheap to build
{{ config(materialized='table') }}

select *
from {{ ref('int_gmpp_unioned') }}
where project_id is null