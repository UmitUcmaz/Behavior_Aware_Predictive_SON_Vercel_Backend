"use client";


type LiveProgress = {
  status: string;
  stage: string;
  stage_label: string;
  current_step: number;
  total_steps: number;
  active_cells: number;
  total_cells: number;
  rows_generated: number;
  expected_rows: number;
  failed_cells: number;
  progress_percent: number;
  elapsed_seconds: number;
};


type Props = {
  // FORECAST-EXECUTION-GENERATE-V1
  inputMode:
    | "upload"
    | "generate";

  generationState:
    | "idle"
    | "generating"
    | "generated"
    | "error";

  generationProgress: number;
  generationStageLabel: string;

  inspectionState: string;
  runState: string;
  totalCells: number | null;
  horizonSteps: number;
  expectedRows: number | null;
  progress: LiveProgress | null;
};


function numberFormat(
  value: number | null | undefined
) {

  if (
    value === null ||
    value === undefined
  ) {
    return "—";
  }

  return new Intl.NumberFormat(
    "en-US"
  ).format(value);
}


export default function ForecastExecutionStatus({
  inputMode,
  generationState,
  generationProgress,
  generationStageLabel,
  inspectionState,
  runState,
  totalCells,
  horizonSteps,
  expectedRows,
  progress,
}: Props) {

  const generationActive =
    inputMode === "generate" &&
    generationState === "generating";

  const generationComplete =
    inputMode === "upload" ||
    generationState === "generated";

  const generationFailed =
    inputMode === "generate" &&
    generationState === "error";

  const generationCompleteWaiting =
    inputMode === "generate" &&
    generationState === "generated" &&
    runState === "idle";

  const generationContext =
    generationActive ||
    generationCompleteWaiting;


  const stage =
    progress?.stage ??
    (
      inspectionState === "validated"
        ? "data_validation"
        : "idle"
    );


  const stageOrder = {
    idle: 0,
    data_validation: 1,
    feature_engineering: 2,
    recursive_forecasting: 3,
    finalizing: 4,
    completed: 5,
    error: -1,
  } as Record<string, number>;


  const currentOrder =
    stageOrder[stage] ?? 0;


  const stageClass = (
    targetOrder: number
  ) => {

    if (
      runState === "error"
    ) {
      return "waiting-dot";
    }

    if (
      currentOrder >
      targetOrder
    ) {
      return "complete-dot";
    }

    if (
      currentOrder ===
      targetOrder
    ) {
      return (
        stage === "completed"
          ? "complete-dot"
          : "active-dot"
      );
    }

    return "waiting-dot";
  };


  const progressPercent =
    progress?.progress_percent ??
    (
      runState === "completed"
        ? 100
        : 0
    );


  const currentStep =
    progress?.current_step ?? 0;

  const activeCells =
    progress?.active_cells ??
    totalCells;

  const generatedRows =
    progress?.rows_generated ?? 0;

  const targetRows =
    progress?.expected_rows ??
    expectedRows;

  const elapsed =
    progress?.elapsed_seconds ?? 0;


  const stageLabel =
    generationActive
      ? generationStageLabel
      : generationFailed
        ? "Generation Failed"
        : runState === "completed"
          ? "Completed"
          : runState === "error"
            ? "Failed"
            : progress?.stage_label ??
              (
                inspectionState ===
                "validated"
                  ? "Dataset Validated"
                  : inspectionState ===
                      "inspecting"
                    ? "Data Validation"
                    : inspectionState ===
                        "error"
                      ? "Validation Failed"
                      : generationState ===
                          "generated"
                        ? "Dataset Generated"
                        : "Ready"
              );


  return (
    <div className="forecast-status-panel">

      <div className="forecast-section-title">

        <span>
          ◈
        </span>

        <h2>
          Execution Status
        </h2>

      </div>


      <div className="forecast-status-body forecast-status-v2">


        <div
          className={
            "forecast-status-ring " +
            (
              (
                runState === "running" ||
                generationActive ||
                inspectionState ===
                  "inspecting"
              )
                ? "processing"
                : ""
            )
          }
          style={{
            background:
              generationContext
                ? `conic-gradient(#19c8ff 0deg,#19c8ff ${generationProgress * 3.6}deg,#083457 ${generationProgress * 3.6}deg)`
                : runState === "completed"
                  ? "conic-gradient(#19c8ff 0deg,#19c8ff 360deg,#083457 360deg)"
                  : runState === "running"
                    ? `conic-gradient(#19c8ff 0deg,#19c8ff ${progressPercent * 3.6}deg,#083457 ${progressPercent * 3.6}deg)`
                    : undefined,
          }}
        >

          <div>
            {generationContext
              ? `${Math.round(
                  generationProgress
                )}%`
              : generationFailed
                ? "ERR"
                : runState === "running"
                  ? `${Math.round(
                      progressPercent
                    )}%`
                  : runState === "completed"
                    ? "100%"
                    : inspectionState ===
                        "inspecting"
                      ? <span style={{ fontSize: "11px", lineHeight: 1.2 }}>Validating</span>
                      : inspectionState ===
                          "validated"
                        ? "OK"
                        : inspectionState ===
                            "error"
                          ? "ERR"
                          : "0%"}
          </div>

        </div>


        <div className="forecast-status-list forecast-stage-list">

          <div>
            <span
              className={
                generationComplete
                  ? "complete-dot"
                  : generationActive
                    ? "active-dot"
                    : "waiting-dot"
              }
            />

            {inputMode === "upload"
              ? "Generate Data (Skipped)"
              : "Generate Data"}
          </div>


          <div>
            <span
              className={
                inspectionState === "validated" ||
                currentOrder > 1
                  ? "complete-dot"
                  : inspectionState ===
                      "inspecting"
                    ? "active-dot"
                    : "waiting-dot"
              }
            />
            Data Validation
          </div>

          <div>
            <span
              className={
                stageClass(2)
              }
            />
            Feature Engineering
          </div>

          <div>
            <span
              className={
                stageClass(3)
              }
            />
            Recursive Forecasting
          </div>

          <div>
            <span
              className={
                stageClass(4)
              }
            />
            Finalizing Output
          </div>

        </div>


        <div className="forecast-live-progress">

          <div className="forecast-live-progress-head">

            <span>
              Current Stage
            </span>

            <strong
              className={
                (
                  runState === "error" ||
                  generationFailed ||
                  inspectionState ===
                    "error"
                )
                  ? "error"
                  : ""
              }
            >
              {stageLabel}
            </strong>

          </div>


          <div className="forecast-live-progress-grid">

            <div>
              <span>
                Step
              </span>

              <strong>
                {generationContext
                  ? "—"
                  : `${currentStep} / ${progress?.total_steps ?? horizonSteps}`}
              </strong>
            </div>


            <div>
              <span>
                {generationContext
                  ? "Cells Requested"
                  : "Cells in Batch"}
              </span>

              <strong>
                {numberFormat(
                  activeCells
                )}
              </strong>
            </div>


            <div>
              <span>
                Rows Generated
              </span>

              <strong>
                {generationContext
                  ? "—"
                  : `${numberFormat(generatedRows)} / ${numberFormat(targetRows)}`}
              </strong>
            </div>


            <div>
              <span>
                Progress
              </span>

              <strong>
                {(
                  generationContext
                    ? generationProgress
                    : progressPercent
                ).toFixed(
                  1
                )}
                %
              </strong>
            </div>


            <div>
              <span>
                Elapsed
              </span>

              <strong>
                {elapsed.toFixed(
                  1
                )}
                {" s"}
              </strong>
            </div>


            <div>
              <span>
                Failed
              </span>

              <strong>
                {generationContext
                  ? "—"
                  : numberFormat(
                      progress?.failed_cells ??
                      0
                    )}
              </strong>
            </div>

          </div>

        </div>

      </div>

    </div>
  );
}
