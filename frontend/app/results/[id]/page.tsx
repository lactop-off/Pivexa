"use client";

import { use, useEffect, useState } from "react";
import { api, ApiError, type AnalysisResult, type Interpretation } from "../../../lib/api";
import { useRequireAuth } from "../../../lib/useRequireAuth";
import { ResultView } from "../../../components/ResultView";

export default function ResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ready = useRequireAuth();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return;
    api
      .get(`/results/${id}`)
      .then((d) => {
        setResult(d.result);
        setInterpretation(d.interpretation);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "取得に失敗しました。"));
  }, [ready, id]);

  if (!ready) return <p className="muted">読み込み中...</p>;
  if (error) return <p className="error">{error}</p>;
  if (!result || !interpretation) return <p className="muted">読み込み中...</p>;

  return <ResultView result={result} interpretation={interpretation} resultId={Number(id)} />;
}
