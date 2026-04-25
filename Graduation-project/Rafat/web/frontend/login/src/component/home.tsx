import React, { useState, useEffect } from "react";

const BASE_URL = "http://localhost:8000"; 

const Home: React.FC = () => {
  const [users, setUsers] = useState<any[]>([]);
  const [machines, setMachines] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Strict Security State
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authCreds, setAuthCreds] = useState({ username: "", password: "" });
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  // Modal States
  const [showUserModal, setShowUserModal] = useState(false);
  const [showMachineModal, setShowMachineModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Form states
  const defaultEmp = { id: "", user_name: "", password: "", devices_assigned: "", role_commend: "employee" };
  const defaultMac = { id: "", name: "", model: "", status: "online", device_ip: "" };
  const [empForm, setEmpForm] = useState(defaultEmp);
  const [macForm, setMacForm] = useState(defaultMac);

  const fetchData = () => {
    setLoading(true);
    Promise.all([
      fetch(`${BASE_URL}/users`).then(r => r.json()),
      fetch(`${BASE_URL}/machines`).then(r => r.json())
    ]).then(([u, m]) => {
      if (Array.isArray(u)) setUsers(u);
      if (Array.isArray(m)) setMachines(m);
    }).catch(err => console.error("Backend offline", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  // ─── Strict Security Wrapper ───
  // EVERY time an action is requested, require password
  const executeWithAuth = (action: () => void) => {
    setPendingAction(() => action);
    setAuthCreds({ username: "", password: "" }); // Clear old passwords
    setShowAuthModal(true);
  };

  const handleAdminAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${BASE_URL}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(authCreds)
      });
      if (res.ok) {
        setShowAuthModal(false);
        if (pendingAction) {
          pendingAction(); // Execute the saved action ONLY if password is correct
          setPendingAction(null);
        }
      } else {
        const err = await res.json();
        alert(`❌ Access Denied:\n${err.detail}`);
      }
    } catch (e) { alert("❌ Server Error connecting to Auth endpoint."); }
  };

  // ─── Actions ───
  const actuallySaveUser = async () => {
    const url = isEditing ? `${BASE_URL}/users/${empForm.id}` : `${BASE_URL}/users`;
    const method = isEditing ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method, 
        headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify({ ...empForm, user_name: empForm.user_name.trim() })
      });
      if (res.ok) {
        setShowUserModal(false);
        fetchData();
      } else {
        const err = await res.json();
        alert(`❌ Database Error:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error`); }
  };

  const actuallySaveMachine = async () => {
    const url = isEditing ? `${BASE_URL}/machines/${macForm.id}` : `${BASE_URL}/machines`;
    const method = isEditing ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method, 
        headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify({ ...macForm, id: parseInt(macForm.id), name: macForm.name.trim(), model: macForm.model.trim() })
      });
      if (res.ok) {
        setShowMachineModal(false);
        fetchData();
      } else {
        const err = await res.json();
        alert(`❌ Database Error:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error`); }
  };

  const actuallyDeleteUser = async (id: string) => {
    const res = await fetch(`${BASE_URL}/users/${id}`, { method: "DELETE" });
    if (res.ok) setUsers(users.filter(u => u.id !== id));
  };

  const actuallyDeleteMachine = async (id: number) => {
    const res = await fetch(`${BASE_URL}/machines/${id}`, { method: "DELETE" });
    if (res.ok) setMachines(machines.filter(m => m.id !== id));
  };

  // Form Submit Handlers (These wrap the actual save with the Auth Gate)
  const handleUserFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeWithAuth(actuallySaveUser);
  };

  const handleMachineFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeWithAuth(actuallySaveMachine);
  };

  const openUserModal = (user: any = null) => {
    if (user) {
      setIsEditing(true);
      // Empty the password so it doesn't overwrite unless they type a new one
      setEmpForm({ ...user, password: "" }); 
    } else {
      setIsEditing(false);
      setEmpForm(defaultEmp);
    }
    setShowUserModal(true);
  };

  const openMachineModal = (machine: any = null) => {
    if (machine) {
      setIsEditing(true);
      setMacForm({ ...machine, id: machine.id.toString() });
    } else {
      setIsEditing(false);
      setMacForm(defaultMac);
    }
    setShowMachineModal(true);
  };

  const statusBadge = (text: string, type: "good" | "bad" | "warn") => {
    const colors = { good: "#22c55e", bad: "#ef4444", warn: "#f59e0b" };
    const color = colors[type];
    return (
      <span style={{ padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 600, display: "inline-flex", background: `${color}22`, color: color, border: `1px solid ${color}55` }}>
        {text.toUpperCase()}
      </span>
    );
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.logo}><span style={{color: "#38bdf8"}}>EVOX</span>AI</div>
        <div>
          <span style={{fontSize: 12, color: "#f59e0b", border: "1px solid #f59e0b", padding: "4px 8px", borderRadius: 4}}>Strict Security Mode: ON</span>
        </div>
      </header>

      <main style={styles.main}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 36 }}>
          <h1 style={{fontSize: 28, fontWeight: 700, margin: 0}}>Management Console</h1>
          <button onClick={fetchData} style={{background: "transparent", border: "1px solid #38bdf8", color: "#38bdf8", padding: "8px 16px", borderRadius: 8, cursor: "pointer"}}>↻ Refresh</button>
        </div>

        {loading ? <div style={{textAlign: "center", marginTop: 50}}>Loading...</div> : (
          <div style={styles.grid}>
            
            {/* ── Employees Table ── */}
            <section style={styles.card}>
              <div style={styles.cardHeader}>
                <h2 style={{fontSize: 16, margin: 0}}>Employees</h2>
                <button style={styles.addBtn} onClick={() => openUserModal()}>+ Add Employee</button>
              </div>
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>ID</th>
                      <th style={styles.th}>User</th>
                      <th style={styles.th}>Devices (Range)</th> {/* Added to view */}
                      <th style={styles.th}>Role</th>
                      <th style={{...styles.th, textAlign: "center"}}>Actions</th>
                      <th style={{...styles.th, textAlign: "right"}}>IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => (
                      <tr key={u.id} style={styles.tr}>
                        <td style={styles.td}>#{u.id}</td>
                        <td style={{...styles.td, fontWeight: 600}}>{u.user_name}</td>
                        <td style={{...styles.td, color: "#94a3b8"}}>{u.devices_assigned || "—"}</td>
                        <td style={styles.td}>{statusBadge(u.role_commend, u.role_commend === "manager" ? "warn" : "good")}</td>
                        <td style={{...styles.td, textAlign: "center"}}>
                          <div style={{display: "flex", gap: "8px", justifyContent: "center"}}>
                            <button style={styles.editBtn} onClick={() => openUserModal(u)}>Edit</button>
                            <button style={styles.deleteBtn} onClick={() => {
                                if(window.confirm(`Delete Employee #${u.id}?`)) executeWithAuth(() => actuallyDeleteUser(u.id))
                            }}>Remove</button>
                          </div>
                        </td>
                        <td style={{...styles.td, fontFamily: "monospace", color: "#38bdf8", textAlign: "right"}}>{u.last_ip || "N/A"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* ── Machines Table ── */}
            <section style={styles.card}>
              <div style={styles.cardHeader}>
                <h2 style={{fontSize: 16, margin: 0}}>Devices</h2>
                <button style={styles.addBtn} onClick={() => openMachineModal()}>+ Add Device</button>
              </div>
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>ID</th>
                      <th style={styles.th}>Name</th>
                      <th style={styles.th}>Status</th>
                      <th style={{...styles.th, textAlign: "center"}}>Actions</th>
                      <th style={{...styles.th, textAlign: "right"}}>IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {machines.map(m => (
                      <tr key={m.id} style={styles.tr}>
                        <td style={styles.td}>#{m.id}</td>
                        <td style={{...styles.td, fontWeight: 600}}>{m.name}</td>
                        <td style={styles.td}>{statusBadge(m.status, m.status === "online" ? "good" : "bad")}</td>
                        <td style={{...styles.td, textAlign: "center"}}>
                          <div style={{display: "flex", gap: "8px", justifyContent: "center"}}>
                            <button style={styles.editBtn} onClick={() => openMachineModal(m)}>Edit</button>
                            <button style={styles.deleteBtn} onClick={() => {
                                if(window.confirm(`Delete Device #${m.id}?`)) executeWithAuth(() => actuallyDeleteMachine(m.id))
                            }}>Remove</button>
                          </div>
                        </td>
                        <td style={{...styles.td, fontFamily: "monospace", color: "#38bdf8", textAlign: "right"}}>{m.device_ip || "N/A"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

          </div>
        )}
      </main>

      {/* ── Security Auth Modal (Triggers on Save/Delete) ── */}
      {showAuthModal && (
        <div style={{...styles.modalOverlay, zIndex: 9999}}> {/* Highest z-index to overlay forms */}
          <div style={{...styles.modalBackground, height: 400}}>
            <div style={{...styles.shape, background: "linear-gradient(#1845ad, #23a2f6)", left: -80, top: -80}} />
            <div style={{...styles.shape, background: "linear-gradient(to right, #ff512f, #f09819)", right: -30, bottom: -80}} />
            <form onSubmit={handleAdminAuth} style={styles.glassForm}>
              <button type="button" onClick={() => { setShowAuthModal(false); setPendingAction(null); }} style={styles.closeBtn}>✕</button>
              <h3 style={styles.formTitle}>Authorization</h3>
              <p style={{textAlign: "center", fontSize: 12, color: "#f59e0b", marginBottom: 20}}>Password required to execute this action.</p>
              
              <label style={styles.label}>Manager Username</label>
              <input style={styles.input} type="text" placeholder="Username" required autoFocus value={authCreds.username} onChange={e => setAuthCreds({...authCreds, username: e.target.value})} />
              <label style={styles.label}>Manager Password</label>
              <input style={styles.input} type="password" placeholder="Password" required value={authCreds.password} onChange={e => setAuthCreds({...authCreds, password: e.target.value})} />
              
              <button type="submit" style={{...styles.submitBtn, marginTop: 25}}>Confirm Action</button>
            </form>
          </div>
        </div>
      )}

      {/* ── Add/Edit Modals ── */}
      {(showUserModal || showMachineModal) && (
        <div style={styles.modalOverlay}>
          <div style={{...styles.modalBackground, height: 650}}> {/* Increased height to fit all fields */}
            <div style={{...styles.shape, background: "linear-gradient(#1845ad, #23a2f6)", left: -80, top: -80}} />
            <div style={{...styles.shape, background: "linear-gradient(to right, #ff512f, #f09819)", right: -30, bottom: -80}} />
            
            {showUserModal ? (
              <form onSubmit={handleUserFormSubmit} style={styles.glassForm}>
                <button type="button" onClick={() => setShowUserModal(false)} style={styles.closeBtn}>✕</button>
                <h3 style={styles.formTitle}>{isEditing ? "Edit Employee" : "Add Employee"}</h3>
                
                <label style={styles.label}>Employee ID</label>
                <input style={styles.input} type="text" placeholder="e.g. 15975" required disabled={isEditing} value={empForm.id} onChange={e => setEmpForm({...empForm, id: e.target.value})} />

                <label style={styles.label}>Username</label>
                <input style={styles.input} type="text" placeholder="Username" required value={empForm.user_name} onChange={e => setEmpForm({...empForm, user_name: e.target.value})} />

                {/* ADDED DEVICES ASSIGNED RANGE HERE */}
                <label style={styles.label}>Assigned Devices (Range)</label>
                <input style={styles.input} type="text" placeholder="e.g. 3101-3110" value={empForm.devices_assigned} onChange={e => setEmpForm({...empForm, devices_assigned: e.target.value})} />

                <label style={styles.label}>{isEditing ? "New Password (Leave blank to keep current)" : "Password"}</label>
                <input style={styles.input} type="password" placeholder="Password" required={!isEditing} value={empForm.password} onChange={e => setEmpForm({...empForm, password: e.target.value})} />

                <label style={styles.label}>Role</label>
                <select style={styles.input} value={empForm.role_commend} onChange={e => setEmpForm({...empForm, role_commend: e.target.value})}>
                  <option value="employee">Employee</option>
                  <option value="manager">Manager</option>
                </select>

                <button type="submit" style={styles.submitBtn}>{isEditing ? "Save Changes" : "Register User"}</button>
              </form>
            ) : (
              <form onSubmit={handleMachineFormSubmit} style={styles.glassForm}>
                <button type="button" onClick={() => setShowMachineModal(false)} style={styles.closeBtn}>✕</button>
                <h3 style={styles.formTitle}>{isEditing ? "Edit Device" : "Create Device"}</h3>
                
                <label style={styles.label}>Device ID</label>
                <input style={styles.input} type="number" placeholder="e.g. 3101" required disabled={isEditing} value={macForm.id} onChange={e => setMacForm({...macForm, id: e.target.value})} />

                <label style={styles.label}>Machine Name</label>
                <input style={styles.input} type="text" placeholder="e.g. ROV-Alpha" required value={macForm.name} onChange={e => setMacForm({...macForm, name: e.target.value})} />

                <label style={styles.label}>Model</label>
                <input style={styles.input} type="text" placeholder="e.g. EX-3000" required value={macForm.model} onChange={e => setMacForm({...macForm, model: e.target.value})} />

                <label style={styles.label}>Device IP Address</label>
                <input style={styles.input} type="text" placeholder="e.g. 192.168.1.50" value={macForm.device_ip} onChange={e => setMacForm({...macForm, device_ip: e.target.value})} />

                <button type="submit" style={styles.submitBtn}>{isEditing ? "Save Changes" : "Register Device"}</button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#080710", color: "#ffffff", fontFamily: "'Poppins', sans-serif" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "20px 40px", borderBottom: "1px solid rgba(255,255,255,0.07)" },
  logo: { fontSize: 24, fontWeight: "bold" },
  main: { maxWidth: 1400, margin: "0 auto", padding: "40px" },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 30, alignItems: "start" },
  card: { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16 },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "20px", borderBottom: "1px solid rgba(255,255,255,0.07)" },
  addBtn: { padding: "8px 18px", background: "linear-gradient(135deg, #0ea5e9, #38bdf8)", border: "none", borderRadius: 8, color: "#fff", cursor: "pointer" },
  tableWrapper: { overflowX: "auto", padding: "10px 20px" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: { padding: "12px 10px", textAlign: "left", color: "#64748b", textTransform: "uppercase", borderBottom: "1px solid rgba(255,255,255,0.07)" },
  tr: { borderBottom: "1px solid rgba(255,255,255,0.04)" },
  td: { padding: "12px 10px" },
  
  editBtn: { background: "rgba(56, 189, 248, 0.1)", border: "1px solid rgba(56, 189, 248, 0.3)", color: "#38bdf8", padding: "4px 10px", borderRadius: 4, cursor: "pointer", fontSize: 11 },
  deleteBtn: { background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#ef4444", padding: "4px 8px", borderRadius: 4, cursor: "pointer", fontSize: 11 },
  
  modalOverlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  modalBackground: { width: 430, position: "relative" },
  shape: { height: 200, width: 200, position: "absolute", borderRadius: "50%" },
  glassForm: { position: "absolute", height: "100%", width: 400, backgroundColor: "rgba(255,255,255,0.13)", transform: "translate(-50%, -50%)", top: "50%", left: "50%", borderRadius: 10, backdropFilter: "blur(10px)", border: "2px solid rgba(255,255,255,0.1)", boxShadow: "0 0 40px rgba(8,7,16,0.6)", padding: "40px 35px", boxSizing: "border-box" },
  formTitle: { fontSize: 28, fontWeight: 500, textAlign: "center", margin: "0 0 10px 0", color: "#fff" },
  label: { display: "block", marginTop: 15, fontSize: 12, fontWeight: 500, color: "#fff", textTransform: "uppercase" },
  input: { display: "block", height: 40, width: "100%", backgroundColor: "rgba(255,255,255,0.07)", borderRadius: 3, padding: "0 10px", marginTop: 5, fontSize: 13, color: "#fff", border: "none", outline: "none", boxSizing: "border-box" },
  submitBtn: { marginTop: 30, width: "100%", backgroundColor: "#ffffff", color: "#080710", padding: "12px 0", fontSize: 16, fontWeight: 600, borderRadius: 5, cursor: "pointer", border: "none" },
  closeBtn: { position: "absolute", top: 15, right: 20, background: "transparent", border: "none", color: "#fff", cursor: "pointer", fontSize: 20, fontWeight: "bold", zIndex: 10 }
};

export default Home;