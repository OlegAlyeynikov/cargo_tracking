import { useRef, useState } from 'react'

export default function DropZone({ onFile }) {
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState(null)
  const inputRef = useRef()

  const handle = (file) => {
    if (!file) return
    setFileName(file.name)
    onFile(file)
  }

  return (
    <div
      onClick={() => inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files[0]) }}
      className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors
        ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={e => handle(e.target.files[0])}
      />
      <div className="text-4xl mb-2">📂</div>
      {fileName
        ? <p className="text-sm font-medium text-blue-700">{fileName}</p>
        : <>
            <p className="text-sm font-medium text-gray-700">Drop CSV or Excel file here</p>
            <p className="text-xs text-gray-400 mt-1">or click to browse — .csv, .xlsx</p>
          </>
      }
    </div>
  )
}
