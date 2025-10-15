import { useState } from 'react'
import './App.css'
import StaffView from './StaffView.jsx'
import CustomerView from './CustomerView.jsx'

function App() {
  const [view, setView] = useState('staff')

  return (
    <div className="app">
      <div className="header" style={{ alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>Mô hình bãi gửi xe thông minh</h1>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            onClick={() => setView('staff')}
            className={view === 'staff' ? 'capture-btn' : ''}
          >
            Giao diện nhân viên
          </button>
          <button
            onClick={() => setView('customer')}
            className={view === 'customer' ? 'capture-btn' : ''}
          >
            Giao diện khách
          </button>
        </div>
      </div>

      <div style={{ paddingTop: 16 }}>
        {view === 'staff' ? <StaffView /> : <CustomerView />}
      </div>
    </div>
  )
}

export default App
