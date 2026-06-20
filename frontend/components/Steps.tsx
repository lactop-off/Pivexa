const STEPS = ["アップロード", "前処理", "設定", "実行", "結果・解釈"];

export function Steps({ current }: { current: number }) {
  return (
    <div className="steps">
      {STEPS.map((s, i) => (
        <span key={s} className={`step${i === current ? " active" : ""}`}>
          {i + 1}. {s}
        </span>
      ))}
    </div>
  );
}
