import { useEffect, useRef, useState } from 'react'

// The svg is built and escaped by the server (one <g class="step"> per step), so it is safe to inject.
export default function Diagram({ svg, captions }: { svg: string; captions: string[] }) {
  const [step, setStep] = useState(0)
  const [big, setBig] = useState(false)
  const last = captions.length - 1
  const view = (
    <div className={'diagram' + (big ? ' big' : '')}>
      <Steps svg={svg} step={step} />
      <p className="caption">{captions[step]}</p>
      <div className="stepper">
        <button disabled={step === 0} onClick={() => setStep(step - 1)}>‹</button>
        <span>{step + 1} / {captions.length}</span>
        <button disabled={step === last} onClick={() => setStep(step + 1)}>›</button>
        <button className="enlarge" onClick={() => setBig(!big)}>{big ? 'Close' : 'Enlarge'}</button>
      </div>
    </div>
  )
  if (!big) return view
  return (
    <div className="scrim" onClick={() => setBig(false)}>
      <div className="settings" onClick={(e) => e.stopPropagation()}>{view}</div>
    </div>
  )
}

function Steps({ svg, step }: { svg: string; step: number }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    box.current?.querySelectorAll<SVGGElement>('g.step').forEach((g, i) => { g.style.display = i <= step ? '' : 'none' })
  }, [svg, step])
  return <div ref={box} dangerouslySetInnerHTML={{ __html: svg }} />
}
