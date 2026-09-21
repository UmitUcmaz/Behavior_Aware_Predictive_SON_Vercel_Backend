"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";


type Point = {
  time: string;
  actual: number;
  forecast: number;
};


type ChartResponse = {
  status: string;
  validation_id: string;
  cell_name: string;
  kpi: string;
  points: Point[];
};


type Props = {
  apiBaseUrl: string;
  validationId: string | null;
  cells: string[];
  kpis: string[];
};


function kpiLabel(
  kpi: string
) {

  if (
    kpi ===
    "UL_PRB_UTILIZATION"
  ) {
    return "UL PRB Utilization";
  }

  if (
    kpi ===
    "DL_PRB_UTILIZATION"
  ) {
    return "DL PRB Utilization";
  }

  if (
    kpi ===
    "ACTIVE_USERS"
  ) {
    return "Active Users";
  }

  return kpi;
}


function valueLabel(
  value: number,
  kpi: string
) {

  if (
    kpi.includes(
      "PRB_UTILIZATION"
    )
  ) {
    return `${value.toFixed(1)}%`;
  }

  return value.toFixed(1);
}


export default function ValidationComparisonChart({
  apiBaseUrl,
  validationId,
  cells,
  kpis,
}: Props) {

  const [
    selectedCell,
    setSelectedCell,
  ] = useState("");

  const [
    selectedKpi,
    setSelectedKpi,
  ] = useState("");

  const [
    data,
    setData,
  ] =
    useState<ChartResponse | null>(
      null
    );

  const [
    loading,
    setLoading,
  ] =
    useState(false);

  const [
    error,
    setError,
  ] =
    useState<string | null>(
      null
    );


  useEffect(() => {

    if (
      cells.length > 0
      && !cells.includes(
        selectedCell
      )
    ) {
      setSelectedCell(
        cells[0]
      );
    }

  }, [
    cells,
    selectedCell,
  ]);


  useEffect(() => {

    if (
      kpis.length > 0
      && !kpis.includes(
        selectedKpi
      )
    ) {
      setSelectedKpi(
        kpis[0]
      );
    }

  }, [
    kpis,
    selectedKpi,
  ]);


  useEffect(() => {

    if (
      !validationId
      || !selectedCell
      || !selectedKpi
    ) {
      setData(null);
      return;
    }

    const controller =
      new AbortController();


    async function load() {

      setLoading(true);
      setError(null);

      try {

        const params =
          new URLSearchParams({
            cell_name:
              selectedCell,
            kpi:
              selectedKpi,
          });

        const response =
          await fetch(
            `${apiBaseUrl}/validation/${validationId}/chart?${params.toString()}`,
            {
              signal:
                controller.signal,
              cache:
                "no-store",
            }
          );

        if (!response.ok) {

          let detail =
            `Chart request failed (${response.status}).`;

          try {

            const body =
              await response.json();

            if (body?.detail) {
              detail =
                String(
                  body.detail
                );
            }

          } catch {
          }

          throw new Error(
            detail
          );
        }

        const body:
          ChartResponse =
            await response.json();

        setData(body);

      } catch (
        loadError
      ) {

        if (
          loadError
          instanceof DOMException
          && loadError.name
          === "AbortError"
        ) {
          return;
        }

        setError(
          loadError
          instanceof Error
            ? loadError.message
            : "Unable to load chart."
        );

      } finally {
        setLoading(false);
      }
    }

    void load();

    return () => {
      controller.abort();
    };

  }, [
    apiBaseUrl,
    validationId,
    selectedCell,
    selectedKpi,
  ]);


  const geometry =
    useMemo(() => {

      if (
        !data
        || data.points.length === 0
      ) {
        return null;
      }

      const points =
        data.points.map(
          (
            point
          ) => ({
            ...point,
            timestamp:
              new Date(
                point.time
              ).getTime(),
          })
        );

      const width = 1000;
      const height = 290;

      const left = 62;
      const right = 24;
      const top = 18;
      const bottom = 38;

      const times =
        points.map(
          (point) =>
            point.timestamp
        );

      const values =
        points.flatMap(
          (point) => [
            point.actual,
            point.forecast,
          ]
        );

      const minTime =
        Math.min(
          ...times
        );

      const maxTime =
        Math.max(
          ...times
        );

      let minValue =
        Math.min(
          ...values
        );

      let maxValue =
        Math.max(
          ...values
        );

      if (
        minValue ===
        maxValue
      ) {
        minValue -= 1;
        maxValue += 1;
      }

      const padding =
        (
          maxValue
          - minValue
        ) * 0.08;

      minValue -= padding;
      maxValue += padding;


      const x = (
        timestamp: number
      ) =>
        left
        + (
          (
            timestamp
            - minTime
          )
          / (
            maxTime
            - minTime || 1
          )
        )
        * (
          width
          - left
          - right
        );


      const y = (
        value: number
      ) =>
        top
        + (
          (
            maxValue
            - value
          )
          / (
            maxValue
            - minValue
          )
        )
        * (
          height
          - top
          - bottom
        );


      const path = (
        key:
          "actual"
          | "forecast"
      ) =>
        points
          .map(
            (
              point,
              index
            ) =>
              `${
                index === 0
                  ? "M"
                  : "L"
              } ${x(
                point.timestamp
              ).toFixed(2)} ${y(
                point[key]
              ).toFixed(2)}`
          )
          .join(" ");


      const yTicks =
        Array.from(
          {
            length: 5,
          },
          (
            _,
            index
          ) => {

            const ratio =
              index / 4;

            return {
              value:
                maxValue
                - (
                  maxValue
                  - minValue
                )
                * ratio,

              y:
                top
                + ratio
                * (
                  height
                  - top
                  - bottom
                ),
            };
          }
        );


      const xTicks =
        Array.from(
          {
            length: 6,
          },
          (
            _,
            index
          ) => {

            const ratio =
              index / 5;

            return {
              timestamp:
                minTime
                + (
                  maxTime
                  - minTime
                )
                * ratio,

              x:
                left
                + ratio
                * (
                  width
                  - left
                  - right
                ),
            };
          }
        );


      return {
        width,
        height,
        left,
        right,
        top,
        bottom,
        actualPath:
          path(
            "actual"
          ),
        forecastPath:
          path(
            "forecast"
          ),
        yTicks,
        xTicks,
      };

    }, [
      data,
    ]);


  return (
    <div className="validation-chart-panel">

      <div className="validation-chart-header">

        <div className="validation-section-title">

          <span>
            ⌁
          </span>

          <h2>
            Forecast vs Actual
          </h2>

        </div>


        <div className="validation-chart-controls">

          <label>
            Cell ID

            <select
              value={
                selectedCell
              }
              disabled={
                !validationId
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedCell(
                    event.target.value
                  )
              }
            >

              {cells.length === 0 ? (
                <option>
                  No validation
                </option>
              ) : (
                cells.map(
                  (
                    cell
                  ) => (
                    <option
                      key={cell}
                      value={cell}
                    >
                      {cell}
                    </option>
                  )
                )
              )}

            </select>

          </label>


          <label>
            KPI

            <select
              value={
                selectedKpi
              }
              disabled={
                !validationId
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedKpi(
                    event.target.value
                  )
              }
            >

              {kpis.length === 0 ? (
                <option>
                  No validation
                </option>
              ) : (
                kpis.map(
                  (
                    kpi
                  ) => (
                    <option
                      key={kpi}
                      value={kpi}
                    >
                      {kpiLabel(
                        kpi
                      )}
                    </option>
                  )
                )
              )}

            </select>

          </label>

        </div>

      </div>


      {!validationId ? (

        <div className="validation-chart-empty">
          Upload actual data and run validation.
        </div>

      ) : loading ? (

        <div className="validation-chart-empty">
          Loading comparison data...
        </div>

      ) : error ? (

        <div className="validation-chart-empty error">
          {error}
        </div>

      ) : data && geometry ? (

        <div className="validation-live-chart">

          <div className="validation-chart-legend">

            <span className="actual">
              Actual
            </span>

            <span className="predicted">
              Forecast
            </span>

            <small>
              {data.points.length} matched points
            </small>

          </div>


          <svg
            viewBox={`0 0 ${geometry.width} ${geometry.height}`}
            preserveAspectRatio="none"
            className="validation-chart-svg"
          >

            {geometry.yTicks.map(
              (
                tick,
                index
              ) => (
                <g
                  key={`y-${index}`}
                >

                  <line
                    x1={
                      geometry.left
                    }
                    x2={
                      geometry.width
                      - geometry.right
                    }
                    y1={tick.y}
                    y2={tick.y}
                    className="validation-grid-line"
                  />

                  <text
                    x={
                      geometry.left
                      - 10
                    }
                    y={
                      tick.y
                      + 4
                    }
                    textAnchor="end"
                    className="validation-axis-text"
                  >
                    {valueLabel(
                      tick.value,
                      selectedKpi
                    )}
                  </text>

                </g>
              )
            )}


            {geometry.xTicks.map(
              (
                tick,
                index
              ) => (
                <g
                  key={`x-${index}`}
                >

                  <line
                    x1={tick.x}
                    x2={tick.x}
                    y1={
                      geometry.top
                    }
                    y2={
                      geometry.height
                      - geometry.bottom
                    }
                    className="validation-grid-line vertical"
                  />

                  <text
                    x={tick.x}
                    y={
                      geometry.height
                      - 11
                    }
                    textAnchor={
                      index === 0
                        ? "start"
                        : index
                          === geometry.xTicks.length - 1
                          ? "end"
                          : "middle"
                    }
                    className="validation-axis-text"
                  >
                    {new Date(
                      tick.timestamp
                    ).toLocaleString(
                      "en-GB",
                      {
                        day:
                          "2-digit",
                        month:
                          "short",
                        hour:
                          "2-digit",
                        minute:
                          "2-digit",
                      }
                    )}
                  </text>

                </g>
              )
            )}


            <path
              d={
                geometry.actualPath
              }
              className="validation-actual-line"
            />

            <path
              d={
                geometry.forecastPath
              }
              className="validation-forecast-line"
            />

          </svg>

        </div>

      ) : null}

    </div>
  );
}
