import React from 'react';
import { Subject } from '../types';

interface SubjectSelectorProps {
  subjects: Subject[];
  selectedSubjectId: number;
  onSubjectChange: (id: number) => void;
}

export const SubjectSelector: React.FC<SubjectSelectorProps> = ({
  subjects,
  selectedSubjectId,
  onSubjectChange,
}) => {
  const currentSubject = subjects.find((s) => s.id === selectedSubjectId);

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-2xs">
      <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
        <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 text-xs flex items-center justify-center font-bold">2</span>
          Step 2: Select Subject
        </h2>
        <span className="text-xs text-slate-500 font-medium">Subject Name only</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
        <div className="md:col-span-2">
          <label className="block text-xs font-medium text-slate-700 mb-1">Subject Name</label>
          <select
            value={selectedSubjectId}
            onChange={(e) => onSubjectChange(Number(e.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {subjects.map((sub) => (
              <option key={sub.id} value={sub.id}>
                {sub.name}
              </option>
            ))}
          </select>
        </div>

        <div className="text-xs bg-slate-50 border border-slate-200 rounded p-2 text-slate-600">
          <div className="font-semibold text-slate-800">Domain Note</div>
          <div>Students remain bound to the class cohort; subject selection defines the assessment context only.</div>
        </div>
      </div>
    </div>
  );
};
