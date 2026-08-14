import { ChannelRail } from '../components/ChannelRail'
import { DetectionFeed } from '../components/DetectionFeed'
import { Spectrogram } from '../components/Spectrogram'
import { AlignmentView } from '../components/AlignmentView'
import { RigStrip } from '../components/RigStrip'
import { RigTwin } from '../components/twin/RigTwin'
import { useStreamStore } from '../store/streamStore'

/** Three-zone cockpit: channel rail · twin · spectrogram+feed (§28). */
export function MonitorScreen() {
  const selected = useStreamStore((s) => s.selected)

  return (
    <div className="screen monitor">
      <div className="cockpit">
        <ChannelRail />
        <div className="center">
          <RigTwin />
        </div>
        <div className="right">
          <div className="right-top">
            <Spectrogram />
          </div>
          <div className="right-mid">
            <DetectionFeed />
          </div>
          <div className="right-bot">
            <AlignmentView detection={selected} />
          </div>
        </div>
      </div>
      <RigStrip />
      <style>{`
        .monitor {
          display: grid;
          grid-template-rows: 1fr var(--strip);
          min-height: 0;
        }
        .cockpit {
          display: grid;
          grid-template-columns: var(--rail) minmax(0, 1.35fr) minmax(280px, 0.95fr);
          gap: 0.5rem;
          padding: 0.5rem;
          min-height: 0;
          height: 100%;
        }
        .center, .right {
          min-height: 0;
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .center { height: 100%; }
        .right-top { flex: 1.1; min-height: 140px; }
        .right-mid { flex: 0.9; min-height: 120px; overflow: hidden; }
        .right-bot { flex: 1; min-height: 160px; }
        @media (max-width: 1100px) {
          .cockpit {
            grid-template-columns: 1fr;
            grid-template-rows: 180px 42vh auto;
            overflow: auto;
          }
          .right { min-height: 520px; }
        }
      `}</style>
    </div>
  )
}
