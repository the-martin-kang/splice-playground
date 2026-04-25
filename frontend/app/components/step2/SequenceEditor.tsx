import type { RefObject } from 'react';
import SequenceDiffView from './SequenceDiffView';
import type { DifferenceSummary, Region } from './types';

interface SequenceEditorProps {
  selectedRegion: Region | null;
  isRegionLoading: boolean;
  currentSequence: string;
  currentOriginalSequence: string;
  editorDisplaySequence: string;
  editorDisplayOriginalSequence: string;
  differenceSummary: DifferenceSummary;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  editorBackdropRef: RefObject<HTMLDivElement | null>;
  onRestoreDiseaseSnv: () => void;
  onRestoreReference: () => void;
  onEditorKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onBeforeInput: (event: React.FormEvent<HTMLTextAreaElement>) => void;
  onPaste: (event: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  onTextareaFallbackChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onEditorScroll: (event: React.UIEvent<HTMLTextAreaElement>) => void;
}

export default function SequenceEditor({
  selectedRegion,
  isRegionLoading,
  currentSequence,
  currentOriginalSequence,
  editorDisplaySequence,
  editorDisplayOriginalSequence,
  differenceSummary,
  textareaRef,
  editorBackdropRef,
  onRestoreDiseaseSnv,
  onRestoreReference,
  onEditorKeyDown,
  onBeforeInput,
  onPaste,
  onTextareaFallbackChange,
  onEditorScroll,
}: SequenceEditorProps) {
  if (!selectedRegion) {
    return (
      <div className="mt-14 rounded-[20px] border border-dashed border-white/16 bg-white/5 p-8 text-center text-slate-800 backdrop-blur-sm">
        <p>위의 Exon 또는 Intron을 클릭하여 서열을 편집하세요</p>
      </div>
    );
  }

  return (
    <div className="mt-14 rounded-[20px] border border-cyan-300/25 bg-white/5 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-lg">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-bold text-slate-950">
          {selectedRegion.region_type === 'exon' ? 'Exon' : 'Intron'} {selectedRegion.region_number} 서열 편집
        </h3>
        <div className="flex flex-wrap gap-2 text-xs text-slate-700">
          <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">길이: {currentSequence.length} bp</span>
          <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">Reference diff: {differenceSummary.toReference}</span>
          <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">Current diff: {differenceSummary.toSeed}</span>
        </div>
      </div>

      {isRegionLoading ? (
        <div className="flex h-32 items-center justify-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
        </div>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              onClick={onRestoreDiseaseSnv}
              className="rounded-full border border-rose-300/55 bg-rose-100/10 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100/15"
            >
              Restore disease SNV
            </button>
            <button
              onClick={onRestoreReference}
              className="rounded-full border border-emerald-300/55 bg-emerald-100/10 px-4 py-2 text-sm font-semibold text-emerald-900 transition hover:bg-emerald-100/15"
            >
              Restore reference
            </button>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-semibold text-slate-800">정상 서열 (Reference)</p>
              <div className="max-h-40 overflow-auto rounded-xl border border-white/16 bg-white/5 p-4 font-mono text-sm leading-6 tracking-normal text-slate-950 [font-variant-ligatures:none] shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] break-all whitespace-pre-wrap [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.45)_rgba(255,255,255,0.08)] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border [&::-webkit-scrollbar-thumb]:border-white/30 [&::-webkit-scrollbar-thumb]:bg-white/45 [&::-webkit-scrollbar-thumb]:backdrop-blur-md [&::-webkit-scrollbar-thumb:hover]:bg-white/65">
                {currentOriginalSequence
                  ? (
                    <SequenceDiffView
                      source={currentOriginalSequence}
                      compareTo={currentSequence}
                      options={{
                        changedClassName: 'bg-amber-300/55 text-slate-950',
                      }}
                    />
                  )
                  : '로딩 중...'}
              </div>
            </div>

            <div>
              <p className="mb-1 text-sm font-semibold text-cyan-800">편집 서열 (고정 길이 overwrite 모드)</p>
              <div className="relative overflow-hidden rounded-xl border border-white/16 bg-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
                <div
                  ref={editorBackdropRef}
                  aria-hidden="true"
                  className="pointer-events-none max-h-56 overflow-auto p-4 font-mono text-sm leading-6 tracking-normal text-slate-950 [font-variant-ligatures:none] whitespace-pre [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.45)_rgba(255,255,255,0.08)] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border [&::-webkit-scrollbar-thumb]:border-white/30 [&::-webkit-scrollbar-thumb]:bg-white/45 [&::-webkit-scrollbar-thumb]:backdrop-blur-md [&::-webkit-scrollbar-thumb:hover]:bg-white/65"
                >
                  <SequenceDiffView
                    source={editorDisplaySequence}
                    compareTo={editorDisplayOriginalSequence}
                    options={{
                      changedClassName: 'bg-amber-300/55 text-slate-950',
                    }}
                  />
                </div>
                <textarea
                  ref={textareaRef}
                  value={editorDisplaySequence}
                  wrap="off"
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                  autoComplete="off"
                  onKeyDown={onEditorKeyDown}
                  onBeforeInput={onBeforeInput}
                  onPaste={onPaste}
                  onChange={onTextareaFallbackChange}
                  onScroll={onEditorScroll}
                  className="absolute inset-0 min-h-full w-full resize-none overflow-auto whitespace-pre bg-transparent p-4 font-mono text-sm leading-6 tracking-normal text-transparent [font-variant-ligatures:none] caret-slate-950 outline-none selection:bg-cyan-200/40 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.45)_rgba(255,255,255,0.08)] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border [&::-webkit-scrollbar-thumb]:border-white/30 [&::-webkit-scrollbar-thumb]:bg-white/45 [&::-webkit-scrollbar-thumb]:backdrop-blur-md [&::-webkit-scrollbar-thumb:hover]:bg-white/65"
                />
              </div>
              <p className="mt-2 text-xs text-slate-700">
                Backspace/Delete는 길이를 줄이지 않고 해당 위치를 <span className="font-bold">N</span>으로 바꿉니다. 입력/붙여넣기는 항상 기존 길이를 유지한 채 덮어쓰기됩니다.
              </p>
            </div>
          </div>
          {differenceSummary.toReference > 0 && (
            <p className="mt-3 text-sm text-rose-800">⚠️ 정상 서열(Reference)과 비교해 {differenceSummary.toReference}개 위치가 다릅니다.</p>
          )}
        </>
      )}
    </div>
  );
}
