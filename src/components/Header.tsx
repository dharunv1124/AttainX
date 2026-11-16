import React from 'react';
import instituteHeader from '../assets/institute-header.png.jpeg.png';

interface HeaderProps {
  onNavigateHome: () => void;
  onNavigateOBEAnalysis: () => void;
  showCourseOBEButton: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  onNavigateHome,
  onNavigateOBEAnalysis,
  showCourseOBEButton,
}) => {
  return (
    <>
      {/* TOP SECTION — LOGO ONLY */}
      <header className="border-t-4 border-emerald-700 border-b border-slate-200 bg-white shadow-xs">
        <div className="mx-auto flex max-w-7xl justify-center px-4 py-0 sm:px-6">
          <img
            src={instituteHeader}
            alt="Manakula Vinayagar Institute of Technology"
            className="app-brand-logo block h-auto max-w-full object-contain"
          />
        </div>
      </header>

      {/* SECOND SECTION — SOFTWARE TITLE + COURSE OBE */}
      <div className="app-title-bar border-b border-slate-200">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2 sm:px-6">
          <button
            type="button"
            onClick={onNavigateHome}
            className="app-title-button w-fit cursor-pointer rounded text-left transition-colors hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            Outcome Based Education
          </button>

          {showCourseOBEButton && (
            <button
              type="button"
              onClick={onNavigateOBEAnalysis}
              className="shrink-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            >
              CO PO Attainment
            </button>
          )}
        </div>
      </div>
    </>
  );
};