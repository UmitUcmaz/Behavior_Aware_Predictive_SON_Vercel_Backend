"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";


type ChartPoint = {
  time: string;
  value: number;
};


type ChartResponse = {
  status: string;
  run_id: string;
  cell_name: string;
  kpi: string;
  source_column: string;
  forecast_column: string;
  history_points: number;
  forecast_points: number;
  historical: ChartPoint[];
  forecast: ChartPoint[];
};


type Props = {
  apiBaseUrl: string;
  runId: string | null;
  cells: string[];
  kpis: string[];
  horizonSteps: number;
  horizonLabel: string;
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


function formatValue(
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


export default function ForecastTrafficChart({
  apiBaseUrl,
  runId,
  cells,
  kpis,
  horizonSteps,
  horizonLabel,
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
    chartData,
    setChartData,
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
      cells.length > 0 &&
      !cells.includes(
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
      kpis.length > 0 &&
      !kpis.includes(
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
      !runId ||
      !selectedCell ||
      !selectedKpi
    ) {
      setChartData(null);
      return;
    }


    const controller =
      new AbortController();


    async function loadChart() {

      setLoading(true);

      setError(null);


      try {

        const params =
          new URLSearchParams({
            cell_name:
              selectedCell,
            kpi:
              selectedKpi,
            history_points:
              "96",
          });


        const response =
          await fetch(
            `${apiBaseUrl}/forecast/${runId}/chart?${params.toString()}`,
            {
              signal:
                controller.signal,
            }
          );


        if (!response.ok) {

          let detail =
            `Chart request failed (${response.status}).`;

          try {

            const body =
              await response.json();

            if (
              body?.detail
            ) {
              detail =
                String(
                  body.detail
                );
            }

          } catch {
            // Keep generic message.
          }

          throw new Error(
            detail
          );
        }


        const data:
          ChartResponse =
            await response.json();


        setChartData(
          data
        );

      } catch (
        loadError
      ) {

        if (
          loadError instanceof DOMException &&
          loadError.name ===
            "AbortError"
        ) {
          return;
        }

        if (
          loadError instanceof Error
        ) {
          setError(
            loadError.message
          );
        } else {
          setError(
            "Unable to load chart data."
          );
        }

      } finally {

        setLoading(false);
      }
    }


    void loadChart();


    return () => {
      controller.abort();
    };

  }, [
    apiBaseUrl,
    runId,
    selectedCell,
    selectedKpi,
  ]);


  const geometry =
    useMemo(() => {

      if (!chartData) {
        return null;
      }


      const historical =
        chartData.historical.map(
          (point) => ({
            ...point,
            timestamp:
              new Date(
                point.time
              ).getTime(),
          })
        );

      const forecast =
        chartData.forecast.map(
          (point) => ({
            ...point,
            timestamp:
              new Date(
                point.time
              ).getTime(),
          })
        );


      const allPoints = [
        ...historical,
        ...forecast,
      ];


      if (
        allPoints.length === 0
      ) {
        return null;
      }


      const width = 1000;
      const height = 270;

      const left = 62;
      const right = 24;
      const top = 18;
      const bottom = 38;


      const timestamps =
        allPoints.map(
          (point) =>
            point.timestamp
        );

      const values =
        allPoints.map(
          (point) =>
            point.value
        );


      const minTime =
        Math.min(
          ...timestamps
        );

      const maxTime =
        Math.max(
          ...timestamps
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
        minValue === maxValue
      ) {
        minValue -= 1;
        maxValue += 1;
      }


      const padding =
        (
          maxValue -
          minValue
        ) * 0.08;


      minValue -= padding;
      maxValue += padding;


      const x = (
        timestamp: number
      ) => {

        if (
          maxTime === minTime
        ) {
          return left;
        }

        return (
          left +
          (
            (
              timestamp -
              minTime
            ) /
            (
              maxTime -
              minTime
            )
          ) *
          (
            width -
            left -
            right
          )
        );
      };


      const y = (
        value: number
      ) => {

        return (
          top +
          (
            (
              maxValue -
              value
            ) /
            (
              maxValue -
              minValue
            )
          ) *
          (
            height -
            top -
            bottom
          )
        );
      };


      const toPath = (
        points:
          typeof historical
      ) => {

        return points
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
                point.value
              ).toFixed(2)}`
          )
          .join(" ");
      };


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

            const value =
              maxValue -
              (
                maxValue -
                minValue
              ) *
              ratio;

            return {
              value,
              y:
                top +
                ratio *
                (
                  height -
                  top -
                  bottom
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

            const timestamp =
              minTime +
              (
                maxTime -
                minTime
              ) *
              ratio;

            return {
              timestamp,
              x:
                left +
                ratio *
                (
                  width -
                  left -
                  right
                ),
            };
          }
        );


      const boundaryTime =
        forecast.length > 0
          ? forecast[0].timestamp
          : null;


      return {
        width,
        height,
        left,
        right,
        top,
        bottom,
        minValue,
        maxValue,
        historical,
        forecast,
        historicalPath:
          toPath(
            historical
          ),
        forecastPath:
          toPath(
            forecast
          ),
        yTicks,
        xTicks,
        boundaryX:
          boundaryTime === null
            ? null
            : x(
                boundaryTime
              ),
      };

    }, [
      chartData,
    ]);


  return (
    <div className="forecast-chart-panel">

      <div className="forecast-chart-header">

        <div className="forecast-section-title">

          <span>
            ⌁
          </span>

          <h2>
            Traffic Forecast
          </h2>

        </div>


        <div className="forecast-chart-controls">

          <label>
            Cell ID

            <select
              value={
                selectedCell
              }
              disabled={
                !runId ||
                cells.length === 0
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedCell(
                    event
                      .target
                      .value
                  )
              }
            >

              {cells.length === 0 ? (
                <option>
                  No forecast
                </option>
              ) : (
                cells.map(
                  (
                    cell
                  ) => (
                    <option
                      key={
                        cell
                      }
                      value={
                        cell
                      }
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
                !runId ||
                kpis.length === 0
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedKpi(
                    event
                      .target
                      .value
                  )
              }
            >

              {kpis.length === 0 ? (
                <option>
                  No forecast
                </option>
              ) : (
                kpis.map(
                  (
                    kpi
                  ) => (
                    <option
                      key={
                        kpi
                      }
                      value={
                        kpi
                      }
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


          <label>
            Horizon

            <div className="forecast-control-display">
              {horizonSteps} Steps · {horizonLabel}
            </div>

          </label>

        </div>

      </div>


      {!runId ? (

        <div className="forecast-real-chart-placeholder">

          <div className="forecast-chart-placeholder-grid" />

          <div className="forecast-chart-placeholder-content">

            <span>
              Waiting for forecast data
            </span>

            <strong>
              Validate a dataset and run forecasting.
            </strong>

          </div>

        </div>

      ) : loading ? (

        <div className="forecast-real-chart-placeholder">

          <div className="forecast-chart-placeholder-grid" />

          <div className="forecast-chart-placeholder-content">

            <span>
              Loading chart
            </span>

            <strong>
              Loading selected cell and KPI data...
            </strong>

          </div>

        </div>

      ) : error ? (

        <div className="forecast-real-chart-placeholder">

          <div className="forecast-chart-placeholder-grid" />

          <div className="forecast-chart-placeholder-content">

            <span className="forecast-chart-error-title">
              Chart unavailable
            </span>

            <strong>
              {error}
            </strong>

          </div>

        </div>

      ) : (
        chartData &&
        geometry && (

          <div className="forecast-live-chart">

            <div className="forecast-live-chart-meta">

              <div>

                <span className="forecast-legend-line historical" />

                Historical

                <small>
                  {chartData.history_points} points
                </small>

              </div>


              <div>

                <span className="forecast-legend-line future" />

                Forecast

                <small>
                  {chartData.forecast_points} points
                </small>

              </div>


              <div className="forecast-chart-source">

                Source:
                {" "}
                {chartData.source_column}

              </div>

            </div>


            <svg
              viewBox={`0 0 ${geometry.width} ${geometry.height}`}
              className="forecast-live-chart-svg"
              preserveAspectRatio="none"
            >

              {geometry.yTicks.map(
                (
                  tick,
                  index
                ) => (
                  <g
                    key={
                      `y-${index}`
                    }
                  >

                    <line
                      x1={
                        geometry.left
                      }
                      x2={
                        geometry.width -
                        geometry.right
                      }
                      y1={
                        tick.y
                      }
                      y2={
                        tick.y
                      }
                      className="forecast-grid-line"
                    />

                    <text
                      x={
                        geometry.left -
                        10
                      }
                      y={
                        tick.y + 4
                      }
                      textAnchor="end"
                      className="forecast-axis-text"
                    >
                      {formatValue(
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
                    key={
                      `x-${index}`
                    }
                  >

                    <line
                      x1={
                        tick.x
                      }
                      x2={
                        tick.x
                      }
                      y1={
                        geometry.top
                      }
                      y2={
                        geometry.height -
                        geometry.bottom
                      }
                      className="forecast-grid-line vertical"
                    />

                    <text
                      x={
                        tick.x
                      }
                      y={
                        geometry.height -
                        12
                      }
                      textAnchor={
                        index === 0
                          ? "start"
                          : index ===
                              geometry.xTicks.length -
                              1
                            ? "end"
                            : "middle"
                      }
                      className="forecast-axis-text"
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


              {geometry.boundaryX !==
                null && (

                <>
                  <line
                    x1={
                      geometry.boundaryX
                    }
                    x2={
                      geometry.boundaryX
                    }
                    y1={
                      geometry.top
                    }
                    y2={
                      geometry.height -
                      geometry.bottom
                    }
                    className="forecast-boundary-line"
                  />

                  <text
                    x={
                      geometry.boundaryX +
                      7
                    }
                    y={
                      geometry.top +
                      13
                    }
                    className="forecast-boundary-label"
                  >
                    Forecast Start
                  </text>
                </>

              )}


              <path
                d={
                  geometry.historicalPath
                }
                className="forecast-history-line"
              />


              <path
                d={
                  geometry.forecastPath
                }
                className="forecast-future-line"
              />

            </svg>

          </div>
        )
      )}

    </div>
  );
}
