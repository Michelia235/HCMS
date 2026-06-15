import React, { useEffect, useRef, useState } from 'react'
import { uploadVideo, getJob } from './api'
import UploadPanel from './components/UploadPanel'
import VideoTimeline from './components/VideoTimeline'
import ReportCard from './components/ReportCard'
import CopilotChat from './components/CopilotChat'

export default function App() {
  const [videoId, setVideoId] = useState(null)
  const [job, setJob] = useState(null)         // {status, message, result}
  const [videoUrl, setVideoUrl] = useState(null)
  const [error, setError] = useState(null)
  const videoRef = useRef(null)
  const pollRef = useRef(null)

  const busy = job && (job.status === 'queued' || job.status === 'processing')

  async function handleUpload(file) {
    setError(null)
    setJob(null)
    setVideoUrl(URL.createObjectURL(file))
    try {
      const { video_id } = await uploadVideo(file)
      setVideoId(video_id)
      setJob({ status: 'queued' })
    } catch (e) {
      setError(e.message)
    }
  }

  // poll job status while processing
  useEffect(() => {
    if (!videoId) return
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const j = await getJob(videoId)
        setJob(j)
        if (j.status === 'done' || j.status === 'error') clearInterval(pollRef.current)
      } catch (e) {
        setError(e.message)
        clearInterval(pollRef.current)
      }
    }, 2500)
    return () => clearInterval(pollRef.current)
  }, [videoId])

  const analysis = job?.result || null

  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-4">
        <h1 className="text-xl font-bold text-slate-800">Hand Hygiene Compliance Copilot</h1>
        <p className="text-sm text-slate-500">
          Phat hien tiep xuc & ve sinh tay theo WHO 5 Moments — MVP
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <UploadPanel onUpload={handleUpload} busy={busy} />
          {busy && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-700">
              Dang phan tich video ({job.status})... cho chut.
            </div>
          )}
          {job?.status === 'error' && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              Loi xu ly: {job.message}
            </div>
          )}
          <VideoTimeline analysis={analysis} videoUrl={videoUrl} videoRef={videoRef} />
        </div>

        <div className="space-y-4">
          <ReportCard analysis={analysis} />
          <CopilotChat videoId={videoId} />
        </div>
      </div>
    </div>
  )
}
