{{ config(materialized='table') }}

select * from {{ ref('stg_gmpp_2021') }}
union all
select * from {{ ref('stg_gmpp_2022') }}
union all
select * from {{ ref('stg_gmpp_2023') }}
union all
select * from {{ ref('stg_gmpp_2024') }}
union all
select * from {{ ref('stg_gmpp_2025') }}
union all
select * from {{ ref('stg_gmpp_2026') }}