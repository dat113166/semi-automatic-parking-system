import { useEffect, useRef, useState } from 'react'
import './App.css'

function App() {
  const [currentTime, setCurrentTime] = useState(new Date())
  const [detectedPlate, setDetectedPlate] = useState('')
  const [memberInfo, setMemberInfo] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [cameraError, setCameraError] = useState('')
  const [capturedImage, setCapturedImage] = useState(null)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)

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

  const handleCapture = () => {
    try {
      const video = videoRef.current
      const canvas = canvasRef.current
      if (!video || !canvas) {
        pushNotification('Không có nguồn camera để chụp', 'error')
        return
      }
      const width = video.videoWidth || 640
      const height = video.videoHeight || 480
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      ctx.drawImage(video, 0, 0, width, height)
      const dataUrl = canvas.toDataURL('image/jpeg', 0.9)
      setCapturedImage(dataUrl)

      pushNotification('Đã chụp ảnh biển số', 'success')
      setDetectedPlate('Đang xử lí...')
      setMemberInfo(null)

      // Mô phỏng nhận diện và truy vấn thành viên
      setTimeout(() => {
        const fakePlate = '59A1-123.45'
        setDetectedPlate(fakePlate)
        pushNotification(`Đã nhận diện biển số: ${fakePlate}`, 'success')

        const exampleMembers = {
          '59A1-123.45': {
            name: 'Nguyễn Văn A',
            memberId: 'MEM001',
            phone: '0901 234 567',
            vehicle: 'Xe máy',
            status: 'Còn hạn',
            expiresAt: '31/12/2026'
          }
        }
        const info = exampleMembers[fakePlate] || null
        if (info) {
          setMemberInfo(info)
          pushNotification('Ghi thông tin xe vào thành công', 'success')
        } else {
          pushNotification('Không tìm thấy thành viên đăng kí cho biển số này', 'info')
        }
      }, 1000)
    } catch (err) {
      console.error(err)
      pushNotification('Lỗi khi chụp ảnh', 'error')
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
            <button className="capture-btn" onClick={handleCapture}>Chụp ảnh</button>
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

export default App
