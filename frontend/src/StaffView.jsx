import { useEffect, useRef, useState } from 'react'
import api from './api/client'

function StaffView() {
  const [currentTime, setCurrentTime] = useState(new Date())
  const [detectedPlate, setDetectedPlate] = useState('')
  const [memberInfo, setMemberInfo] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [cameraError, setCameraError] = useState('')
  const [capturedImage] = useState(null)
  const [cardId, setCardId] = useState('')
  const [lane, setLane] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [isPolling, setIsPolling] = useState(false)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const pollRef = useRef(null)

  const pushNotification = (message, type = 'info') => {
    const id = `${Date.now()}-${Math.random()}`
    const time = new Date()
    setNotifications((prev) => [{ id, message, type, time }, ...prev].slice(0, 50))
  }

  const toTitleCase = (str) => str.split(' ').map((w) => w ? w.charAt(0).toLocaleUpperCase('vi-VN') + w.slice(1) : '').join(' ')

  const formatDateLine = (date) => {
    const weekday = new Intl.DateTimeFormat('vi-VN', { weekday: 'long' }).format(date)
    const datePart = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date)
    return `${toTitleCase(weekday)}, ${datePart}`
  }

  const formatTimeLine = (date) => new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date)

  useEffect(() => {
    const id = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    let stream
    const startCamera = async () => {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setCameraError('Trình duyệt không hỗ trợ camera')
          pushNotification('Trình duyệt không hỗ trợ camera', 'error')
          return
        }
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
          audio: false
        })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (err) {
        console.error(err)
        setCameraError('Không thể truy cập camera')
        pushNotification('Không thể truy cập camera', 'error')
      }
    }
    startCamera()
    return () => {
      if (stream) {
        stream.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [])

  const handleCapture = async () => {
    try {
      pushNotification('Khởi tạo phiên và yêu cầu chụp ảnh...', 'info')
      setDetectedPlate('')
      setMemberInfo(null)

      const res = await api.checkIn({
        cardId: cardId || undefined,
        lane: lane || undefined,
        plateText: undefined,
        vehicleType: undefined,
      })
      if (res && res.session_id) {
        setSessionId(res.session_id)
        pushNotification('Đã tạo phiên, đang chờ nhận diện...', 'success')

        // Start polling events for this session until CHECKED_IN with plate_text
        setIsPolling(true)
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = setInterval(async () => {
          try {
            const events = await api.getEvents(50)
            const list = (events && events.events) || []
            const found = list.find(e => e.session_id === res.session_id)
            if (found && found.status === 'CHECKED_IN' && found.plate_text) {
              setDetectedPlate(found.plate_text)
              pushNotification(`Đã nhận diện: ${found.plate_text}`, 'success')
              clearInterval(pollRef.current)
              pollRef.current = null
              setIsPolling(false)
            }
          } catch (err) {
            console.error(err)
          }
        }, 2000)
      } else {
        pushNotification('Không tạo được phiên chụp ảnh', 'error')
      }
    } catch (err) {
      console.error(err)
      const msg = (err && (err.message || (err.data && (err.data.message || err.data.detail)))) || 'Lỗi check-in tới backend'
      pushNotification(msg, 'error')
    }
  }

  return (
    <>
      <div className="app">
        <div className="header">
          <h1>Hệ thống nhận diện biển số xe</h1>
          <div className="clock">
            <div className="clock-date">{formatDateLine(currentTime)}</div>
            <div className="clock-time">{formatTimeLine(currentTime)}</div>
          </div>
        </div>

        <div className="layout">
          <section className="camera-section">
            <div className="camera-frame">
              {cameraError ? (
                <div className="camera-placeholder">{cameraError}</div>
              ) : (
                <video ref={videoRef} className="camera-video" autoPlay playsInline muted />
              )}
              <canvas ref={canvasRef} style={{ display: 'none' }} />
            </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
            <input
              placeholder="Card ID (tuỳ chọn)"
              value={cardId}
              onChange={(e) => setCardId(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, flex: 1 }}
            />
            <input
              placeholder="Lane (tuỳ chọn)"
              value={lane}
              onChange={(e) => setLane(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, width: 160 }}
            />
            <button className="capture-btn" onClick={handleCapture}>Tạo phiên & chụp</button>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#888' }}>
            {sessionId ? `Session: ${sessionId}${isPolling ? ' • Đang nhận diện...' : ''}` : 'Chưa tạo phiên'}
          </div>
          </section>

          <aside className="side-panel">
            <div className="panel capture-panel">
              <div className="panel-title">Ảnh đã chụp</div>
              <div className="capture-preview">
                {capturedImage ? (
                  <img src={capturedImage} alt="Ảnh đã chụp" />
                ) : (
                  <div className="empty">Chưa có ảnh</div>
                )}
              </div>
            </div>
            <div className="panel plate-panel">
              <div className="panel-title">Biển số đã đọc</div>
              <div className="plate-display">{detectedPlate || '—'}</div>
            </div>

            <div className="panel member-panel">
              <div className="panel-title">Thông tin thành viên</div>
              {memberInfo ? (
                <div className="member-info">
                  <div><strong>Tên:</strong> {memberInfo.name}</div>
                  <div><strong>Mã thành viên:</strong> {memberInfo.memberId}</div>
                  <div><strong>SĐT:</strong> {memberInfo.phone}</div>
                  <div><strong>Loại xe:</strong> {memberInfo.vehicle}</div>
                  <div><strong>Trạng thái:</strong> {memberInfo.status}</div>
                  <div><strong>Hạn:</strong> {memberInfo.expiresAt}</div>
                </div>
              ) : (
                <div className="empty">Chưa có thông tin</div>
              )}
            </div>
          </aside>

          <aside className="notifications-column">
            <div className="panel notifications-panel">
              <div className="panel-title">Thông báo</div>
              <ul className="notifications-list">
                {notifications.map((n) => (
                  <li key={n.id} className={`note ${n.type}`}>
                    <span className="note-time">{n.time.toLocaleTimeString('vi-VN')}</span>
                    <span className="note-text">{n.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        </div>
      </div>
    </>
  )
}

export default StaffView


