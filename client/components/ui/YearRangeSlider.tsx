'use client';

import { useCallback } from 'react';

interface YearRangeSliderProps {
  min: number;
  max: number;
  value: [number, number];
  onChange: (range: [number, number]) => void;
  label?: string;
}

export function YearRangeSlider({ min, max, value, onChange, label }: YearRangeSliderProps) {
  const [minVal, maxVal] = value;

  const getPercent = useCallback(
    (val: number) => {
      if (max === min) return 0;
      return Math.round(((val - min) / (max - min)) * 100);
    },
    [min, max],
  );

  const minPercent = getPercent(minVal);
  const maxPercent = getPercent(maxVal);

  return (
    <div className="w-full select-none">
      {label && (
        <label className="block text-sm font-medium text-slate-700 mb-2">{label}</label>
      )}

      {/* Year display */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-md">
          {minVal}
        </span>
        <span className="text-xs text-slate-400 mx-2">—</span>
        <span className="text-sm font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-md">
          {maxVal}
        </span>
      </div>

      {/* Slider track */}
      <div className="relative h-5 flex items-center">
        {/* Background track */}
        <div className="absolute w-full h-1.5 bg-slate-200 rounded-full" />

        {/* Selected range highlight */}
        <div
          className="absolute h-1.5 bg-indigo-500 rounded-full"
          style={{ left: `${minPercent}%`, width: `${maxPercent - minPercent}%` }}
        />

        {/* Min thumb */}
        <input
          type="range"
          min={min}
          max={max}
          value={minVal}
          onChange={(e) => {
            const val = Math.min(Number(e.target.value), maxVal - 1);
            onChange([val, maxVal]);
          }}
          className="year-range-slider absolute w-full h-1.5 appearance-none bg-transparent"
          style={{ zIndex: minVal >= maxVal - 1 ? 5 : 3 }}
        />

        {/* Max thumb */}
        <input
          type="range"
          min={min}
          max={max}
          value={maxVal}
          onChange={(e) => {
            const val = Math.max(Number(e.target.value), minVal + 1);
            onChange([minVal, val]);
          }}
          className="year-range-slider absolute w-full h-1.5 appearance-none bg-transparent"
          style={{ zIndex: 4 }}
        />
      </div>

      {/* Min/Max labels */}
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-slate-400">{min}</span>
        <span className="text-[10px] text-slate-400">{max}</span>
      </div>
    </div>
  );
}
