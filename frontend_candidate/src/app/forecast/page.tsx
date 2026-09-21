"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import ForecastTrafficChart from "@/components/ForecastTrafficChart";
import ForecastExecutionStatus from "@/components/ForecastExecutionStatus";


const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";


type InspectionResponse = {
  status: string;
  input_filename: string;
  input_rows: number;
  total_columns: number;
  total_cells: number;
  total_kpis: number;
  cell_column: string;
  time_column: string;
  kpi_columns: string[];
  valid_timestamp_rows: number;
  invalid_timestamp_rows: number;

  input_date_range: {
    start: string | null;
    end: string | null;
  };
};


type ForecastResponse = {
  status: string;
  run_id: string;
  engine: string;
  input_filename: string;

  horizon_steps: number;
  horizon_minutes: number;

  input_rows: number;

  input_date_range: {
    start: string | null;
    end: string | null;
  };

  total_cells: number;
  successful_cells: number;
  failed_cells: number;

  kpis: string[];

  cells: string[];

  forecast_rows: number;
  forecast_signature: string;

  output_columns: string[];

  runtime_seconds: {
    preprocessing: number;
    forecast_engine: number;
    total: number;
  };

  calls: {
    forecast_model_predict: number;
    recursive_state_update: number;
    clustering_predict: number;
  };

  preview: Record<
    string,
    string | number
  >[];

  download_url: string;
};


type DatasetGenerationResponse = {
  status?: string;
  generation_id: string;
  cell_count: number;
  seed: number;
  eligible_cell_count: number;
  coverage_threshold: number;
  resolution_minutes: number;
  history_start: string;
  history_end: string;
  cutoff: string;
  ground_truth_start: string;
  ground_truth_end: string;
  forecast_input_rows: number;
  ground_truth_rows: number;
  model_ready_rows?: number | null;
  minimum_history_coverage: number;
  minimum_ground_truth_coverage: number;
  cells?: string[];
  forecast_input_download: string;
  ground_truth_download: string;
  manifest_download: string;
  runtime_seconds?: Record<
    string,
    number
  >;
};


type InspectionState =
  | "idle"
  | "inspecting"
  | "validated"
  | "error";


type RunState =
  | "idle"
  | "running"
  | "completed"
  | "error";


type ForecastJobStatus = {
  status: string;
  run_id: string;
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
  result: ForecastResponse | null;
  error: string | null;
};


type ForecastStreamEvent =
  | {
      type: "connected";
      data: {
        status: string;
      };
    }
  | {
      type: "progress";
      data: ForecastJobStatus;
    }
  | {
      type: "result";
      data: ForecastResponse;
    }
  | {
      type: "error";
      data: {
        message?: string;
      };
    };


type DatasetGenerationProgress = {
  status: string;
  generation_id?: string;
  stage: string;
  stage_label: string;
  cell_count: number;
  progress_percent: number;
  elapsed_seconds: number;
};


type DatasetGenerationStreamEvent =
  | {
      type: "connected";
      data: {
        status: string;
      };
    }
  | {
      type: "progress";
      data: DatasetGenerationProgress;
    }
  | {
      type: "result";
      data: DatasetGenerationResponse;
    }
  | {
      type: "error";
      data: {
        message?: string;
      };
    };


type SessionArtifactIds = {
  generation_id: string | null;
  forecast_run_id: string | null;
};


function postNdjsonStream<TEvent>(
  url: string,
  payload: Record<string, unknown>,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  return new Promise(
    (resolve, reject) => {
      const xhr = new XMLHttpRequest();

      let processedLength = 0;
      let buffer = "";
      let settled = false;

      const rejectOnce = (
        error: unknown
      ) => {
        if (settled) {
          return;
        }

        settled = true;

        try {
          xhr.abort();
        } catch {
          // Ignore abort errors during cleanup.
        }

        reject(
          error instanceof Error
            ? error
            : new Error(String(error))
        );
      };

      const processAvailableText = () => {
        if (settled) {
          return;
        }

        const fullText =
          xhr.responseText ?? "";

        if (
          fullText.length < processedLength
        ) {
          processedLength = 0;
          buffer = "";
        }

        const incoming =
          fullText.slice(
            processedLength
          );

        processedLength =
          fullText.length;

        if (!incoming) {
          return;
        }

        buffer += incoming;

        const lines =
          buffer.split("\n");

        buffer =
          lines.pop() ?? "";

        for (const line of lines) {
          const cleanLine =
            line.trim();

          if (!cleanLine) {
            continue;
          }

          onEvent(
            JSON.parse(
              cleanLine
            ) as TEvent
          );
        }
      };

      xhr.open(
        "POST",
        url,
        true
      );

      xhr.setRequestHeader(
        "Content-Type",
        "application/json"
      );

      xhr.setRequestHeader(
        "Accept",
        "application/x-ndjson"
      );

      xhr.onprogress = () => {
        try {
          processAvailableText();
        } catch (error) {
          rejectOnce(error);
        }
      };

      xhr.onreadystatechange = () => {
        if (
          xhr.readyState !== 3 ||
          settled
        ) {
          return;
        }

        try {
          processAvailableText();
        } catch (error) {
          rejectOnce(error);
        }
      };

      xhr.onload = () => {
        if (settled) {
          return;
        }

        if (
          xhr.status < 200 ||
          xhr.status >= 300
        ) {
          let detail =
            `Request failed (${xhr.status}).`;

          try {
            const body =
              JSON.parse(
                xhr.responseText
              );

            if (body?.detail) {
              detail = String(
                body.detail
              );
            }
          } catch {
            // Keep generic HTTP error.
          }

          rejectOnce(
            new Error(detail)
          );
          return;
        }

        try {
          processAvailableText();

          const tail =
            buffer.trim();

          if (tail) {
            onEvent(
              JSON.parse(
                tail
              ) as TEvent
            );
          }

          buffer = "";
          settled = true;
          resolve();
        } catch (error) {
          rejectOnce(error);
        }
      };

      xhr.onerror = () => {
        rejectOnce(
          new Error(
            "Streaming request failed."
          )
        );
      };

      xhr.onabort = () => {
        if (!settled) {
          rejectOnce(
            new Error(
              "Streaming request was aborted."
            )
          );
        }
      };

      xhr.send(
        JSON.stringify(payload)
      );
    }
  );
}


function openEventSourceStream<TEvent>(
  url: string,
  onEvent: (
    event: TEvent
  ) => boolean | void,
): Promise<void> {
  return new Promise(
    (resolve, reject) => {
      const source =
        new EventSource(url);

      let settled = false;

      const closeAndResolve = () => {
        if (settled) {
          return;
        }

        settled = true;
        source.close();
        resolve();
      };

      const closeAndReject = (
        error: unknown
      ) => {
        if (settled) {
          return;
        }

        settled = true;
        source.close();

        reject(
          error instanceof Error
            ? error
            : new Error(String(error))
        );
      };

      source.onmessage = (
        message
      ) => {
        if (settled) {
          return;
        }

        try {
          const event =
            JSON.parse(
              message.data
            ) as TEvent;

          const shouldClose =
            onEvent(event);

          if (shouldClose) {
            closeAndResolve();
          }

        } catch (error) {
          closeAndReject(error);
        }
      };

      source.onerror = () => {
        if (!settled) {
          closeAndReject(
            new Error(
              "Live progress connection was interrupted."
            )
          );
        }
      };
    }
  );
}


function readStoredArtifactIds(): SessionArtifactIds {
  try {
    return {
      generation_id:
        sessionStorage.getItem(
          "baps_generation_id"
        ),
      forecast_run_id:
        sessionStorage.getItem(
          "baps_active_forecast_run_id"
        ),
    };
  } catch {
    return {
      generation_id: null,
      forecast_run_id: null,
    };
  }
}


function clearStoredArtifactIds() {
  try {
    sessionStorage.removeItem(
      "baps_generation_id"
    );
    sessionStorage.removeItem(
      "baps_ground_truth_download"
    );
    sessionStorage.removeItem(
      "baps_generation_manifest"
    );
    sessionStorage.removeItem(
      "baps_active_forecast_run_id"
    );
    sessionStorage.removeItem(
      "baps_active_forecast_session"
    );
  } catch {
    // Session storage is optional.
  }
}


function clearStoredForecastIds() {
  try {
    sessionStorage.removeItem(
      "baps_active_forecast_run_id"
    );
    sessionStorage.removeItem(
      "baps_active_forecast_session"
    );
  } catch {
    // Session storage is optional.
  }
}


async function requestArtifactCleanup(
  payload: SessionArtifactIds,
  keepalive = false
) {
  if (
    !payload.generation_id &&
    !payload.forecast_run_id
  ) {
    return;
  }

  const response =
    await fetch(
      `${API_BASE_URL}/session/cleanup`,
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json",
        },
        body: JSON.stringify(
          payload
        ),
        keepalive,
      }
    );

  if (!response.ok) {
    throw new Error(
      `Session cleanup failed (${response.status}).`
    );
  }
}


function formatNumber(
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


function formatDate(
  value: string | null | undefined
) {

  if (!value) {
    return "—";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return value;
  }

  return date.toLocaleString(
    "en-GB",
    {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }
  );
}


function ForecastChartPlaceholder({
  state,
}: {
  state: RunState;
}) {

  return (
    <div className="forecast-real-chart-placeholder">

      <div className="forecast-chart-placeholder-grid" />

      <div className="forecast-chart-placeholder-content">

        <span>
          {state === "completed"
            ? "Forecast completed"
            : state === "running"
              ? "Forecast processing"
              : "Waiting for forecast data"}
        </span>

        <strong>
          {state === "completed"
            ? "Cell / KPI chart data will be connected next."
            : state === "running"
              ? "BASELINE-01 is generating predictions."
              : "Validate a dataset and run forecasting."}
        </strong>

      </div>

    </div>
  );
}


export default function ForecastPage() {

  const fileInputRef =
    useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);

  // FORECAST-GENERATE-DATASET-V1
  const [
    inputMode,
    setInputMode,
  ] =
    useState<
      "upload" | "generate"
    >(
      "upload"
    );

  const [
    generatorCellCount,
    setGeneratorCellCount,
  ] =
    useState(
      "100"
    );

  const [
    generationState,
    setGenerationState,
  ] =
    useState<
      | "idle"
      | "generating"
      | "generated"
      | "error"
    >(
      "idle"
    );

  const [
    generation,
    setGeneration,
  ] =
    useState<
      DatasetGenerationResponse | null
    >(
      null
    );


  const [
    generationProgress,
    setGenerationProgress,
  ] =
    useState(
      0
    );

  const [
    generationStageLabel,
    setGenerationStageLabel,
  ] =
    useState(
      "Ready"
    );



  const [horizon, setHorizon] =
    useState("96");

  const [
    inspectionState,
    setInspectionState,
  ] =
    useState<InspectionState>(
      "idle"
    );

  const [
    inspection,
    setInspection,
  ] =
    useState<InspectionResponse | null>(
      null
    );

  const [
    runState,
    setRunState,
  ] =
    useState<RunState>(
      "idle"
    );

  const [
    result,
    setResult,
  ] =
    useState<ForecastResponse | null>(
      null
    );

  const [
    errorMessage,
    setErrorMessage,
  ] =
    useState<string | null>(
      null
    );

  const [
    liveProgress,
    setLiveProgress,
  ] =
    useState<ForecastJobStatus | null>(
      null
    );


  const horizonLabel =
    useMemo(
      () => {

        if (horizon === "12")
          return "3 Hours";

        if (horizon === "24")
          return "6 Hours";

        if (horizon === "48")
          return "12 Hours";

        if (horizon === "96")
          return "24 Hours";

        return `${horizon} Steps`;

      },
      [horizon]
    );


  const totalCells =
    result?.total_cells ??
    inspection?.total_cells ??
    generation?.cell_count ??
    null;

  const totalKpis =
    result?.kpis.length ??
    inspection?.total_kpis ??
    (
      generation
        ? 3
        : null
    );

  const inputRows =
    result?.input_rows ??
    inspection?.input_rows ??
    generation?.forecast_input_rows ??
    null;

  const dateRange =
    result?.input_date_range ??
    inspection?.input_date_range ??
    (
      generation
        ? {
            start:
              generation.history_start,
            end:
              generation.history_end,
          }
        : null
    );


  const expectedRows =
    totalCells
      ? totalCells *
        Number(horizon)
      : null;


  const canRunForecast =
    inputMode === "generate"
      ? (
          generationState ===
            "generated" &&
          generation !== null
        )
      : (
          selectedFile !== null &&
          inspectionState ===
            "validated"
        );


  useEffect(
    () => {
      const cleanupWindow =
        window as Window & {
          __bapsArtifactCleanupInstalled?: boolean;
        };

      if (
        cleanupWindow
          .__bapsArtifactCleanupInstalled
      ) {
        return;
      }

      cleanupWindow
        .__bapsArtifactCleanupInstalled =
          true;

      cleanupWindow.addEventListener(
        "pagehide",
        () => {
          const storedArtifacts =
            readStoredArtifactIds();

          clearStoredArtifactIds();

          void requestArtifactCleanup(
            storedArtifacts,
            true
          ).catch(
            () => {
              // Page teardown cleanup is best-effort.
              // Server-side TTL cleanup is the fallback.
            }
          );
        }
      );
    },
    []
  );


  const resetForecast = () => {

    const storedArtifacts =
      readStoredArtifactIds();

    const cleanupPayload: SessionArtifactIds = {
      generation_id:
        generation?.generation_id ??
        storedArtifacts.generation_id,
      forecast_run_id:
        result?.run_id ??
        storedArtifacts.forecast_run_id,
    };

    void requestArtifactCleanup(
      cleanupPayload
    ).catch(
      () => {
        // Reset must remain responsive even if cleanup
        // temporarily fails. TTL cleanup is the fallback.
      }
    ).finally(
      () => {
        clearStoredArtifactIds();
      }
    );

    setSelectedFile(null);

    setInputMode(
      "upload"
    );

    setGeneratorCellCount(
      "100"
    );

    setGenerationState(
      "idle"
    );

    setGeneration(null);

    setGenerationProgress(
      0
    );

    setGenerationStageLabel(
      "Ready"
    );

    setHorizon("96");

    setInspectionState(
      "idle"
    );

    setInspection(null);

    setRunState(
      "idle"
    );

    setResult(null);

    setErrorMessage(null);

    setLiveProgress(null);

    if (
      fileInputRef.current
    ) {
      fileInputRef.current.value =
        "";
    }
  };


  const inspectFile =
    async (
      file: File
    ) => {

      setInspectionState(
        "inspecting"
      );

      setInspection(null);

      setResult(null);

      setRunState(
        "idle"
      );

      setErrorMessage(null);


      const formData =
        new FormData();

      formData.append(
        "file",
        file
      );


      try {

        const response =
          await fetch(
            `${API_BASE_URL}/forecast/inspect`,
            {
              method: "POST",
              body: formData,
            }
          );


        if (!response.ok) {

          let detail =
            `Dataset validation failed (${response.status}).`;

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
            // Keep generic error.
          }

          throw new Error(
            detail
          );
        }


        const data:
          InspectionResponse =
            await response.json();


        setInspection(
          data
        );

        setInspectionState(
          "validated"
        );

      } catch (
        error
      ) {

        setInspectionState(
          "error"
        );

        if (
          error instanceof Error
        ) {

          setErrorMessage(
            error.message
          );

        } else {

          setErrorMessage(
            "Dataset validation failed."
          );
        }
      }
    };


  const handleSelectedFile =
    async (
      file: File
    ) => {

      setSelectedFile(
        file
      );

      await inspectFile(
        file
      );
    };


  const generateNetworkDataset =
    async () => {

      const requestedCellCount =
        Number(
          generatorCellCount
        );

      if (
        !Number.isFinite(
          requestedCellCount
        ) ||
        requestedCellCount < 1 ||
        requestedCellCount > 2000
      ) {
        setErrorMessage(
          "Please select a valid cell count."
        );
        return;
      }


      const staleArtifacts =
        readStoredArtifactIds();

      if (
        staleArtifacts.generation_id ||
        staleArtifacts.forecast_run_id
      ) {
        try {
          await requestArtifactCleanup(
            staleArtifacts
          );
        } catch {
          // Do not block a new user request because
          // stale cleanup had a temporary network error.
        } finally {
          clearStoredArtifactIds();
        }
      }


      setGenerationState(
        "generating"
      );

      setGeneration(null);

      setSelectedFile(null);

      setInspectionState(
        "idle"
      );

      setInspection(null);

      setResult(null);

      setRunState(
        "idle"
      );

      setErrorMessage(null);

      setGenerationProgress(
        0
      );

      setGenerationStageLabel(
        "Starting Dataset Generation"
      );

      setLiveProgress(
        {
          status: "running",
          run_id: "",
          stage: "idle",
          stage_label:
            "Starting Dataset Generation",
          current_step: 0,
          total_steps:
            Number(horizon),
          active_cells:
            requestedCellCount,
          total_cells:
            requestedCellCount,
          rows_generated: 0,
          expected_rows: 0,
          failed_cells: 0,
          progress_percent: 0,
          elapsed_seconds: 0,
          result: null,
          error: null,
        }
      );


      try {

        const completedGeneration = {
          value:
            null as DatasetGenerationResponse | null,
        };

        const lastGenerationProgress = {
          value:
            null as DatasetGenerationProgress | null,
        };


        await openEventSourceStream<DatasetGenerationStreamEvent>(
          (
            `${API_BASE_URL}/dataset-generator/generate/events`
            + `?cell_count=${encodeURIComponent(
              String(
                requestedCellCount
              )
            )}`
          ),
          (event) => {
            if (
              event.type ===
                "progress"
            ) {
              const generationProgressEvent =
                event.data;

              lastGenerationProgress.value =
                generationProgressEvent;

              setGenerationProgress(
                generationProgressEvent
                  .progress_percent
              );

              setGenerationStageLabel(
                generationProgressEvent
                  .stage_label
              );

              setLiveProgress(
                {
                  status: "running",
                  run_id: "",
                  stage: "idle",
                  stage_label:
                    generationProgressEvent
                      .stage_label,
                  current_step: 0,
                  total_steps:
                    Number(horizon),
                  active_cells:
                    generationProgressEvent
                      .cell_count ||
                    requestedCellCount,
                  total_cells:
                    generationProgressEvent
                      .cell_count ||
                    requestedCellCount,
                  rows_generated: 0,
                  expected_rows: 0,
                  failed_cells: 0,
                  progress_percent:
                    generationProgressEvent
                      .progress_percent,
                  elapsed_seconds:
                    generationProgressEvent
                      .elapsed_seconds,
                  result: null,
                  error: null,
                }
              );

              return;
            }

            if (
              event.type ===
                "result"
            ) {
              completedGeneration.value =
                event.data;
              return true;
            }

            if (
              event.type ===
                "error"
            ) {
              throw new Error(
                event.data.message ??
                "Dataset generation failed."
              );
            }
          }
        );


        if (!completedGeneration.value) {
          throw new Error(
            "Dataset generation stream ended without result data."
          );
        }


        const generationData =
          completedGeneration.value;


        setGeneration(
          generationData
        );

        setGenerationState(
          "generated"
        );

        setGenerationProgress(
          100
        );

        setGenerationStageLabel(
          "Dataset Generated"
        );

        const generationElapsed =
          lastGenerationProgress.value
            ?.elapsed_seconds ??
          generationData
            .runtime_seconds
            ?.total ??
          0;

        setLiveProgress(
          {
            status: "completed",
            run_id: "",
            stage: "data_validation",
            stage_label:
              "Dataset Validated",
            current_step: 0,
            total_steps:
              Number(horizon),
            active_cells:
              generationData.cell_count,
            total_cells:
              generationData.cell_count,
            rows_generated: 0,
            expected_rows: 0,
            failed_cells: 0,
            progress_percent: 100,
            elapsed_seconds:
              generationElapsed,
            result: null,
            error: null,
          }
        );

        // Generated-mode input is created by the
        // trusted backend generator and is already
        // model-ready. No browser download/re-upload
        // or /forecast/inspect request is required.
        setInspectionState(
          "validated"
        );

        setInspection(null);


        try {

          sessionStorage.setItem(
            "baps_generation_id",
            generationData.generation_id
          );

          sessionStorage.setItem(
            "baps_ground_truth_download",
            generationData.ground_truth_download
          );

          sessionStorage.setItem(
            "baps_generation_manifest",
            generationData.manifest_download
          );

        } catch {
          // Session storage is optional.
        }


      } catch (
        error
      ) {

        setGenerationState(
          "error"
        );

        setGenerationStageLabel(
          "Generation Failed"
        );

        setGenerationProgress(
          0
        );

        setLiveProgress(null);

        setSelectedFile(null);

        setInspectionState(
          "idle"
        );

        setInspection(null);


        if (
          error instanceof Error
        ) {

          setErrorMessage(
            error.message
          );

        } else {

          setErrorMessage(
            "Dataset generation failed."
          );
        }
      }
    };


  const runForecast =
    async () => {

      if (
        inputMode === "generate"
      ) {

        if (
          !generation ||
          generationState !==
            "generated"
        ) {
          return;
        }

      } else if (
        !selectedFile ||
        inspectionState !==
          "validated"
      ) {
        return;
      }


      if (
        inputMode === "generate"
      ) {
        const storedArtifacts =
          readStoredArtifactIds();

        const previousRunId =
          result?.run_id ??
          storedArtifacts.forecast_run_id;

        if (previousRunId) {
          try {
            await requestArtifactCleanup(
              {
                generation_id: null,
                forecast_run_id:
                  previousRunId,
              }
            );
          } catch {
            // TTL cleanup is the fallback.
          } finally {
            clearStoredForecastIds();
          }
        }
      }


      setRunState(
        "running"
      );

      setResult(null);

      setErrorMessage(null);


      if (
        inputMode === "generate" &&
        generation
      ) {

        const totalSteps =
          Number(
            horizon
          );

        const expected =
          generation.cell_count *
          totalSteps;

        setLiveProgress(
          {
            status: "running",
            run_id: "",
            stage:
              "recursive_forecasting",
            stage_label:
              "Running Forecast on Vercel",
            current_step: 0,
            total_steps:
              totalSteps,
            active_cells:
              generation.cell_count,
            total_cells:
              generation.cell_count,
            rows_generated: 0,
            expected_rows:
              expected,
            failed_cells: 0,
            progress_percent: 0,
            elapsed_seconds: 0,
            result: null,
            error: null,
          }
        );


        try {

          const completedResult = {
            value:
              null as ForecastResponse | null,
          };


          await openEventSourceStream<ForecastStreamEvent>(
            (
              `${API_BASE_URL}/forecast/generated/events`
              + `?generation_id=${encodeURIComponent(
                generation.generation_id
              )}`
              + `&horizon_steps=${encodeURIComponent(
                String(
                  totalSteps
                )
              )}`
            ),
            (event) => {
              if (
                event.type ===
                  "progress"
              ) {
                setLiveProgress(
                  event.data
                );
                return;
              }

              if (
                event.type ===
                  "result"
              ) {
                completedResult.value =
                  event.data;
                return true;
              }

              if (
                event.type ===
                  "error"
              ) {
                throw new Error(
                  event.data.message ??
                  "Forecast failed."
                );
              }
            }
          );


          if (!completedResult.value) {
            throw new Error(
              "Forecast stream ended without result data."
            );
          }


          const forecastResult =
            completedResult.value;


          setResult(
            forecastResult
          );

          setRunState(
            "completed"
          );

          setLiveProgress(
            {
              status: "completed",
              run_id:
                forecastResult.run_id,
              stage: "completed",
              stage_label: "Completed",
              current_step:
                forecastResult.horizon_steps,
              total_steps:
                forecastResult.horizon_steps,
              active_cells:
                forecastResult.successful_cells,
              total_cells:
                forecastResult.total_cells,
              rows_generated:
                forecastResult.forecast_rows,
              expected_rows:
                forecastResult.total_cells *
                forecastResult.horizon_steps,
              failed_cells:
                forecastResult.failed_cells,
              progress_percent: 100,
              elapsed_seconds:
                forecastResult.runtime_seconds
                  .total,
              result:
                forecastResult,
              error: null,
            }
          );


          try {

            sessionStorage.setItem(
              "baps_active_forecast_run_id",
              forecastResult.run_id
            );

            sessionStorage.setItem(
              "baps_active_forecast_session",
              JSON.stringify(
                {
                  run_id:
                    forecastResult.run_id,
                  generation_id:
                    generation.generation_id,
                  source_type:
                    "generated",
                  horizon_steps:
                    forecastResult.horizon_steps,
                }
              )
            );

          } catch {
            // Session storage is optional.
          }


        } catch (
          error
        ) {

          setRunState(
            "error"
          );

          setLiveProgress(null);

          if (
            error instanceof Error
          ) {

            setErrorMessage(
              error.message
            );

          } else {

            setErrorMessage(
              "An unexpected forecast error occurred."
            );
          }
        }

        return;
      }


      setLiveProgress(null);


      const formData =
        new FormData();

      formData.append(
        "file",
        selectedFile as File
      );

      formData.append(
        "horizon_steps",
        horizon
      );


      try {

        const startResponse =
          await fetch(
            `${API_BASE_URL}/forecast/start`,
            {
              method: "POST",
              body: formData,
            }
          );


        if (!startResponse.ok) {

          let detail =
            `Forecast start failed (${startResponse.status}).`;

          try {

            const body =
              await startResponse.json();

            if (body?.detail) {
              detail =
                String(
                  body.detail
                );
            }

          } catch {
            // Keep generic error.
          }

          throw new Error(
            detail
          );
        }


        const startData:
          ForecastJobStatus =
            await startResponse.json();


        setLiveProgress(
          startData
        );


        const runId =
          startData.run_id;


        while (true) {

          await new Promise(
            (
              resolve
            ) =>
              setTimeout(
                resolve,
                400
              )
          );


          const statusResponse =
            await fetch(
              `${API_BASE_URL}/forecast/${runId}/status`,
              {
                cache: "no-store",
              }
            );


          if (
            !statusResponse.ok
          ) {
            throw new Error(
              (
                "Unable to read live "
                + "forecast status."
              )
            );
          }


          const statusData:
            ForecastJobStatus =
              await statusResponse.json();


          setLiveProgress(
            statusData
          );


          if (
            statusData.status ===
              "completed"
          ) {

            if (
              !statusData.result
            ) {
              throw new Error(
                (
                  "Forecast completed "
                  + "without result data."
                )
              );
            }

            setResult(
              statusData.result
            );

            setRunState(
              "completed"
            );

            break;
          }


          if (
            statusData.status ===
              "error"
          ) {

            throw new Error(
              statusData.error ??
              "Forecast failed."
            );
          }
        }

      } catch (
        error
      ) {

        setRunState(
          "error"
        );

        if (
          error instanceof Error
        ) {

          setErrorMessage(
            error.message
          );

        } else {

          setErrorMessage(
            "An unexpected forecast error occurred."
          );
        }
      }
    };

  const downloadForecast =
    async () => {

      if (!result) {
        return;
      }

      try {
        const response = await fetch(
          `/api/forecast-download?run_id=${encodeURIComponent(result.run_id)}`,
          {
            method: "GET",
            cache: "no-store",
          }
        );

        const payload = await response.json() as {
          status?: string;
          download_url?: string;
          error?: string;
        };

        if (!response.ok || !payload.download_url) {
          throw new Error(
            payload.error ??
            "Could not prepare the forecast CSV download."
          );
        }

        const anchor = document.createElement("a");
        anchor.href = payload.download_url;
        anchor.rel = "noopener";
        anchor.style.display = "none";

        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();

      } catch (error) {

        if (error instanceof Error) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage(
            "An unexpected forecast export error occurred."
          );
        }
      }
    };



  return (
    <div className="forecast-page">


      <section className="forecast-banner">

        <img
          src="/images/home-v6-city-reference.png"
          alt=""
          className="forecast-banner-image"
        />

        <div className="forecast-banner-fade" />


        <div className="forecast-banner-copy">

          <div className="forecast-eyebrow">
            FORECAST
          </div>

          <h1>
            Forecast
          </h1>

          <p>
            Predict future network behavior from
            historical cellular traffic.
          </p>

        </div>


        <div className="forecast-banner-note">

          <span>
            From Data to Foresight.
          </span>

          <strong>
            A Smarter, More Connected World.
          </strong>

          <i />

        </div>

      </section>


      <div className="forecast-main-grid">


        <aside className="forecast-config-panel">

          <div className="forecast-panel-title">

            <div className="forecast-title-icon">
              ⚙
            </div>

            <h2>
              Forecast Configuration
            </h2>

            <button
              type="button"
              className="forecast-reset"
              onClick={
                resetForecast
              }
            >
              ↻ Reset
            </button>

          </div>


          <div className="forecast-input-mode">

            <button
              type="button"
              className={
                inputMode ===
                "upload"
                  ? "active"
                  : ""
              }
              disabled={
                runState ===
                "running"
              }
              onClick={
                () => {

                  if (
                    inputMode ===
                    "upload"
                  ) {
                    return;
                  }

                  resetForecast();

                  setInputMode(
                    "upload"
                  );
                }
              }
            >
              Upload Dataset
            </button>

            <button
              type="button"
              className={
                inputMode ===
                "generate"
                  ? "active"
                  : ""
              }
              disabled={
                runState ===
                "running"
              }
              onClick={
                () => {

                  if (
                    inputMode ===
                    "generate"
                  ) {
                    return;
                  }

                  resetForecast();

                  setInputMode(
                    "generate"
                  );
                }
              }
            >
              Generate Dataset
              <small>
                Network Data
              </small>
            </button>

          </div>




          {inputMode ===
          "upload" ? (

            <>
          <div className="forecast-config-step">

            <div className="forecast-step-label">

              <span>
                1
              </span>

              <strong>
                Upload Network Data (CSV)
              </strong>

            </div>


            <label
              className={
                "forecast-upload-box " +
                (
                  inspectionState ===
                    "validated"
                    ? "validated"
                    : inspectionState ===
                        "inspecting"
                      ? "inspecting"
                      : ""
                )
              }
              onDragOver={
                (
                  event
                ) => {
                  event.preventDefault();
                }
              }
              onDrop={
                (
                  event
                ) => {

                  event.preventDefault();

                  const file =
                    event
                      .dataTransfer
                      .files?.[0];

                  if (file) {
                    void handleSelectedFile(
                      file
                    );
                  }
                }
              }
            >

              <input
                ref={
                  fileInputRef
                }
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={
                  (
                    event
                  ) => {

                    const file =
                      event
                        .target
                        .files?.[0] ??
                      null;

                    if (file) {
                      void handleSelectedFile(
                        file
                      );
                    }
                  }
                }
              />


              <div className="forecast-upload-icon">

                {inspectionState ===
                "validated"
                  ? "✓"
                  : inspectionState ===
                      "inspecting"
                    ? "◌"
                    : "⇧"}

              </div>


              {!selectedFile ? (
                <>
                  <strong>
                    Drag & drop your CSV file here
                  </strong>

                  <span>
                    or click to browse files
                  </span>
                </>
              ) : (
                <>
                  <strong>
                    {selectedFile.name}
                  </strong>

                  <span>
                    {(
                      selectedFile.size /
                      1024 /
                      1024
                    ).toFixed(2)}
                    {" MB"}
                  </span>


                  <small className="forecast-upload-validation">

                    {inspectionState ===
                    "inspecting"
                      ? "Validating dataset..."
                      : inspectionState ===
                          "validated"
                        ? "Dataset validated"
                        : inspectionState ===
                            "error"
                          ? "Validation failed"
                          : ""}

                  </small>
                </>
              )}

            </label>

          </div>
            </>

          ) : (

            <div className="forecast-config-step forecast-generator-step">

              <div className="forecast-step-label">

                <span>
                  1
                </span>

                <strong>
                  Generate Network Dataset
                </strong>

              </div>


              <div className="forecast-generator-card">

                <label
                  className="forecast-generator-label"
                  htmlFor="forecast-generator-cell-count"
                >
                  Number of Cells
                </label>


                <select
                  id="forecast-generator-cell-count"
                  className="forecast-generator-select"
                  value={
                    generatorCellCount
                  }
                  disabled={
                    generationState ===
                      "generating" ||
                    generationState ===
                      "generated" ||
                    runState ===
                      "running"
                  }
                  onChange={
                    (
                      event
                    ) => {

                      setGeneratorCellCount(
                        event.target.value
                      );

                      setGenerationState(
                        "idle"
                      );

                      setGeneration(null);

                      setGenerationProgress(
                        0
                      );

                      setGenerationStageLabel(
                        "Ready"
                      );

                      setSelectedFile(null);

                      setInspectionState(
                        "idle"
                      );

                      setInspection(null);

                      setResult(null);

                      setErrorMessage(null);
                    }
                  }
                >
                  <option value="100">
                    100 Cells
                  </option>

                  <option value="300">
                    300 Cells
                  </option>

                  <option value="500">
                    500 Cells
                  </option>

                  <option value="1000">
                    1,000 Cells
                  </option>

                  <option value="2000">
                    2,000 Cells
                  </option>

                </select>


                <div className="forecast-generator-meta">

                  <span>
                    Real network source
                  </span>

                  <strong>
                    15 min · 98% coverage
                  </strong>

                </div>


                <button
                  type="button"
                  className="forecast-generate-button"
                  disabled={
                    generationState ===
                      "generating" ||
                    generationState ===
                      "generated" ||
                    runState ===
                      "running"
                  }
                  onClick={
                    generateNetworkDataset
                  }
                >

                  <span>
                    {generationState ===
                    "generating"
                      ? "◌"
                      : "✦"}
                  </span>

                  {generationState ===
                  "generating"
                    ? "Generating Dataset..."
                    : generationState ===
                        "generated"
                      ? "Dataset Generated"
                      : "Generate Dataset"}

                </button>


                {generation && (

                  <div className="forecast-generated-result">

                    <div className="forecast-generated-status">

                      <span>
                        ✓
                      </span>

                      <strong>
                        Dataset Generated
                      </strong>

                    </div>


                    <div className="forecast-generated-file">

                      <strong>
                        {generation.cell_count.toLocaleString()}
                        {" Cells"}
                      </strong>

                      <span>
                        {generation.forecast_input_rows.toLocaleString()}
                        {" historical rows"}
                      </span>

                    </div>


                    


                    <div className="forecast-generation-id">

                      <small>
                        GENERATION ID
                      </small>

                      <strong>
                        {generation.generation_id}
                      </strong>

                    </div>

                  </div>
                )}


                {generationState ===
                  "generating" && (

                  <div className="forecast-generator-progress">

                    {generationStageLabel}
                    {" · "}
                    {Math.round(
                      generationProgress
                    )}
                    %

                  </div>
                )}


                <div className="forecast-generator-note">

                  Future ground-truth data is
                  stored separately and is not
                  passed to the Forecast Engine.

                </div>

              </div>

            </div>

          )}


          <div className="forecast-config-step">

            <div className="forecast-step-label">

              <span>
                2
              </span>

              <strong>
                Forecast Horizon
              </strong>

            </div>


            <select
              className="forecast-select"
              value={
                horizon
              }
              disabled={
                runState ===
                "running"
              }
              onChange={
                (
                  event
                ) => {

                  setHorizon(
                    event.target.value
                  );

                  setResult(
                    null
                  );

                  if (
                    runState ===
                    "completed"
                  ) {
                    setRunState(
                      "idle"
                    );
                  }
                }
              }
            >

              <option value="12">
                12 Steps (3 Hours)
              </option>

              <option value="24">
                24 Steps (6 Hours)
              </option>

              <option value="48">
                48 Steps (12 Hours)
              </option>

              <option value="96">
                96 Steps (24 Hours)
              </option>

            </select>

          </div>


          <button
            type="button"
            className="forecast-run-button"
            disabled={
              !canRunForecast ||
              runState ===
                "running"
            }
            onClick={
              runForecast
            }
          >

            <span>
              {runState ===
              "running"
                ? "◌"
                : "▶"}
            </span>

            {runState ===
            "running"
              ? "Running Forecast..."
              : inspectionState ===
                  "inspecting"
                ? "Validating Dataset..."
                : "Run Forecast"}

            <strong>
              ›
            </strong>

          </button>


          {inputMode !== "generate" && <div className="forecast-runtime-note"><span>ⓘ</span><p>Dataset validation runs before forecasting. Forecasting uses the optimized BASELINE-01 engine.</p></div>}


          {errorMessage && (

            <div className="forecast-error-box">

              <strong>
                {generationState ===
                "error"
                  ? "Dataset generation failed"
                  : inspectionState ===
                      "error"
                    ? "Dataset validation failed"
                    : "Forecast failed"}
              </strong>

              <span>
                {errorMessage}
              </span>

            </div>

          )}


          {result && (

            <div className="forecast-run-info">

              <span>
                RUN ID
              </span>

              <strong>
                {result.run_id}
              </strong>

              <small>
                Engine: {result.engine}
              </small>

            </div>

          )}

        </aside>


        <section className="forecast-content">


          <div className="forecast-top-grid">


            <div className="forecast-summary-panel">

              <div className="forecast-section-title">

                <span>
                  ▤
                </span>

                <h2>
                  Dataset Summary
                </h2>


                {inspectionState ===
                  "validated" && (

                  <em className="forecast-validation-badge">
                    Validated
                  </em>

                )}

              </div>


              <div className="forecast-summary-cards">


                <div>

                  <small>
                    Total Cells
                  </small>

                  <strong>
                    {formatNumber(
                      totalCells
                    )}
                  </strong>

                  <span>
                    {inspectionState ===
                    "inspecting"
                      ? "Validating..."
                      : totalCells
                        ? `${totalCells} cells detected`
                        : inputMode === "generate"
                          ? "Generate dataset"
                          : "Upload dataset"}
                  </span>

                </div>


                <div>

                  <small>
                    Total KPIs
                  </small>

                  <strong>
                    {formatNumber(
                      totalKpis
                    )}
                  </strong>

                  <span>
                    {inspection
                      ? `${inspection.total_kpis} required KPI columns`
                      : result
                        ? `${result.kpis.length} forecast KPIs`
                        : generation
                          ? "3 forecast KPIs"
                          : inputMode === "generate"
                            ? "Generate dataset"
                            : "Upload dataset"}
                  </span>

                </div>


                <div>

                  <small>
                    Total Records
                  </small>

                  <strong>
                    {formatNumber(
                      inputRows
                    )}
                  </strong>

                  <span>
                    Historical input rows
                  </span>

                </div>


                <div>

                  <small>
                    Date Range
                  </small>

                  <strong className="forecast-date-value">

                    {dateRange
                      ? formatDate(
                          dateRange.start
                        )
                      : "—"}

                  </strong>

                  <span>

                    {dateRange
                      ? `to ${formatDate(
                          dateRange.end
                        )}`
                      : "Historical coverage"}

                  </span>

                </div>

              </div>

            </div>


            <ForecastExecutionStatus
              inputMode={
                inputMode
              }
              generationState={
                generationState
              }
              generationProgress={
                generationProgress
              }
              generationStageLabel={
                generationStageLabel
              }
              inspectionState={
                inspectionState
              }
              runState={
                runState
              }
              totalCells={
                totalCells
              }
              horizonSteps={
                Number(horizon)
              }
              expectedRows={
                expectedRows
              }
              progress={
                liveProgress
              }
            />

          </div>


          <div className="forecast-bottom-grid">


            <div className="forecast-output-panel">

              <div className="forecast-section-title">

                <span>
                  ▥
                </span>

                <h2>
                  Forecast Output Summary
                </h2>


                <em
                  className={
                    runState ===
                      "completed"
                      ? "completed"
                      : ""
                  }
                >

                  {runState ===
                  "completed"
                    ? "Completed"
                    : "Waiting"}

                </em>

              </div>


              <div className="forecast-output-cards">


                <div>

                  <small>
                    Successful Cells
                  </small>

                  <strong>
                    {result
                      ? formatNumber(
                          result.successful_cells
                        )
                      : "—"}
                  </strong>

                  <span>
                    {result
                      ? `${result.failed_cells} failed`
                      : "Available after forecast"}
                  </span>

                </div>


                <div>

                  <small>
                    Forecast Rows
                  </small>

                  <strong>
                    {result
                      ? formatNumber(
                          result.forecast_rows
                        )
                      : "—"}
                  </strong>

                  <span>
                    Cells × forecast horizon
                  </span>

                </div>


                <div>

                  <small>
                    Total Runtime
                  </small>

                  <strong>
                    {result
                      ? `${result.runtime_seconds.total.toFixed(2)} s`
                      : "—"}
                  </strong>

                  <span>
                    {result
                      ? `Engine ${result.runtime_seconds.forecast_engine.toFixed(2)} s`
                      : "Available after forecast"}
                  </span>

                </div>


                <div>

                  <small>
                    Forecast Horizon
                  </small>

                  <strong>
                    {result
                      ? result.horizon_steps
                      : horizon}
                  </strong>

                  <span>
                    {result
                      ? `${result.horizon_minutes / 60} Hours`
                      : horizonLabel}
                  </span>

                </div>

              </div>

            

              <div className="forecast-output-actions">

                <div className="forecast-output-actions-info">

                  <div className="forecast-output-actions-heading">

                    <span>
                      ▰
                    </span>

                    <strong>
                      Export & Actions
                    </strong>

                  </div>


                  {result ? (

                    <div className="forecast-signature-chip">

                      <span>
                        Signature
                      </span>

                      <strong>
                        {result.forecast_signature}
                      </strong>

                    </div>

                  ) : (

                    <span className="forecast-output-actions-waiting">
                      Available after forecast
                    </span>

                  )}

                </div>


                <button
                  type="button"
                  disabled={
                    !result
                  }
                  className="forecast-export-primary forecast-output-export-button"
                  onClick={
                    downloadForecast
                  }
                >
                  ⇩ Export Forecast CSV
                </button>


                <small className="forecast-export-note forecast-output-export-note">
                  CSV export includes cell, timestamp and KPI predictions.
                </small>

              </div>

</div>


            

          </div>


          <ForecastTrafficChart
            apiBaseUrl={API_BASE_URL}
            runId={
              result?.run_id ?? null
            }
            cells={
              result?.cells ?? []
            }
            kpis={
              result?.kpis ?? []
            }
            horizonSteps={
              Number(horizon)
            }
            horizonLabel={
              horizonLabel
            }
          />

        </section>

      </div>

    </div>
  );
}
