with base as (
    select
        fl_date,
        op_unique_carrier,
        tail_num,
        origin_airport_id,
        dest_airport_id,
        dest,
        dep_delay,
        arr_delay,
        carrier_delay,
        weather_delay,
        nas_delay,
        cancelled,
        cancellation_code
    from {{ source('airspace_raw', 'flights_raw') }}
    where tail_num is not null
),

with_lineage as (
    select
        *,

        -- The previous flight's arrival delay for this same aircraft
        lag(arr_delay) over (
            partition by tail_num
            order by fl_date
        ) as prev_flight_arr_delay,

        -- Which airport this aircraft just came from
        lag(origin_airport_id) over (
            partition by tail_num
            order by fl_date
        ) as prev_flight_origin_airport_id,

        -- How much of today's departure delay was inherited
        case
            when dep_delay > 0 and lag(arr_delay) over (
                partition by tail_num
                order by fl_date
            ) > 0
            then least(dep_delay, lag(arr_delay) over (
                partition by tail_num
                order by fl_date
            ))
            else 0
        end as inherited_delay_minutes,

        -- Root cause classification
        case
            when cast(cancelled as int64) = 1 and cancellation_code = 'A' then 'carrier_cancellation'
            when cast(cancelled as int64) = 1 and cancellation_code = 'B' then 'weather_cancellation'
            when cast(cancelled as int64) = 1 and cancellation_code = 'C' then 'nas_cancellation'
            when carrier_delay > 0 and (weather_delay is null or weather_delay = 0)
                then 'carrier_controlled'
            when weather_delay > 0 and (carrier_delay is null or carrier_delay = 0)
                then 'weather_controlled'
            when nas_delay > 0 and (carrier_delay is null or carrier_delay = 0)
                then 'faa_controlled'
            when carrier_delay > 0 and weather_delay > 0
                then 'mixed_carrier_weather'
            else 'unknown'
        end as delay_root_cause

    from base
)

select * from with_lineage