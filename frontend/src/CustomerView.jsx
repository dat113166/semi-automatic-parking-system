import { useEffect, useRef, useState } from 'react'

function CustomerView() {
  const [notification, setNotification] = useState('')
  const [plate, setPlate] = useState('')
  const [member, setMember] = useState(null)
  const [cameraError, setCameraError] = useState('')

  const videoRef = useRef(null)
  const canvasRef = useRef(null)

  useEffect(() => {
    let stream
    const startCamera = async () => {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setCameraError('Trình duyệt không hỗ trợ camera')
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
      }
    }
    startCamera()
    return () => {
      if (stream) {
        stream.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  const handleRecognize = () => {
    setNotification('Nhận diện xe thành công!')
    setPlate('30F-123.45')
    setMember({
      name: 'Nguyễn Văn A',
      memberId: 'MEM-2025-0001',
      phone: '0901 234 567',
      vehicle: 'Xe máy',
      status: 'Còn hiệu lực',
      expiresAt: '31/12/2025'
    })
  }

  return (
    <>
      <div className="app">
        <div className="header">
          <h1>Giao diện khách hàng</h1>
        </div>

        <div
          style={{
            fontSize: 24,
            fontWeight: 700,
            minHeight: 36,
            color: notification ? '#16a34a' : '#aaa',
            margin: '0 16px 12px'
          }}
        >
          {notification || 'Vui lòng đưa xe vào khung hình camera'}
        </div>

        <div className="layout" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <section className="camera-section">
            <div className="camera-frame">
              {cameraError ? (
                <div className="camera-placeholder">{cameraError}</div>
              ) : (
                <video ref={videoRef} className="camera-video" autoPlay playsInline muted />
              )}
              <canvas ref={canvasRef} style={{ display: 'none' }} />
            </div>
            <button className="capture-btn" onClick={handleRecognize}>nhận diện xe</button>
          </section>

          <aside className="side-panel">
            <div className="panel plate-panel">
              <div className="panel-title">Biển số đã đọc</div>
              <div className="plate-display">{plate || '—'}</div>
            </div>

            <div className="panel member-panel">
              <div className="panel-title">Thông tin thành viên</div>
              {member ? (
                <div className="member-info">
                  <div><strong>Tên:</strong> {member.name}</div>
                  <div><strong>Mã thành viên:</strong> {member.memberId}</div>
                  <div><strong>SĐT:</strong> {member.phone}</div>
                  <div><strong>Loại xe:</strong> {member.vehicle}</div>
                  <div><strong>Trạng thái:</strong> {member.status}</div>
                  <div><strong>Hạn:</strong> {member.expiresAt}</div>
                </div>
              ) : (
                <div className="empty">Chưa có thông tin</div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </>
  )
}

export default CustomerView


