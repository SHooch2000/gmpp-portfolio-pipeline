{{ config(materialzed='table')}}

select {{ dbt_utils.generate_surrogate_key(['department']) }} as department_key,
       max(department) as department_name
from {{ ref('int_gmpp_unioned') }}
where department is not null
group by department
