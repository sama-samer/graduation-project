import React, { useState, useEffect } from "react";

interface Employee {
  id: string; 
  user_name: string;
  devices_assigned: string;
  role_commend: string;
}

interface Machine {
  id: number;
  name: string;
  model: string;
  status: "online" | "offline" | "maintenance";
}

interface ModalProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

const Modal: React.FC<ModalProps> = ({ title, onClose, children }) => (
  <div style={styles.overlay} onClick={onClose}>
    <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
      <div style={styles.modalHeader}>
        <span style={styles.modalTitle}>{title}</span>
        <button style={styles.closeBtn} onClick={onClose}>✕</button>
      </div>
      <div style={styles.modalBody}>{children}</div>
    </div>
  </div>
);

// ─── Add User Form ────────────────────────────────────────────────────────────
const AddUserForm: React.FC<{ onClose: () => void; onAdd: (user: any) => void }> = ({ onClose, onAdd }) => {
  const [form, setForm] = useState({
    id: "",
    user_name: "",
    password: "",
    devices_assigned: "",
    role_commend: "employee"
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd({
      id: form.id.trim(), 
      user_name: form.user_name.trim(),
      password: form.password,
      devices_assigned: form.devices_assigned.trim(),
      role_commend: form.role_commend
    });
  };

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <div style={styles.field}>
        <label style={styles.label}>Employee ID</label>
        <input style={styles.input} type="number" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} required placeholder="e.g. 15975" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Username</label>
        <input style={styles.input} value={form.user_name} onChange={(e) => setForm({ ...form, user_name: e.target.value })} required placeholder="e.g. ahmed_rayan" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Password</label>
        <input style={styles.input} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required placeholder="Enter secure password" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Devices Assigned Range</label>
        <input style={styles.input} value={form.devices_assigned} onChange={(e) => setForm({ ...form, devices_assigned: e.target.value })} placeholder="e.g. 3101-3110 or 3105" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Role</label>
        <select style={styles.input} value={form.role_commend} onChange={(e) => setForm({ ...form, role_commend: e.target.value })}>
          <option value="employee">Employee</option>
          <option value="manager">Manager</option>
        </select>
      </div>
      <div style={styles.formActions}>
        <button type="button" style={styles.cancelBtn} onClick={onClose}>Cancel</button>
        <button type="submit" style={styles.submitBtn}>Add User</button>
      </div>
    </form>
  );
};

// ─── Add Machine Form ─────────────────────────────────────────────────────────
const AddMachineForm: React.FC<{ onClose: () => void; onAdd: (m: any) => void }> = ({ onClose, onAdd }) => {
  const [form, setForm] = useState({
    id: "",
    name: "",
    model: "",
    status: "online" as "online" | "offline" | "maintenance",
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd({
      id: parseInt(form.id),
      name: form.name.trim(),
      model: form.model.trim(),
      status: form.status,
    });
  };

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <div style={styles.field}>
        <label style={styles.label}>Device ID (Number only)</label>
        <input style={styles.input} type="number" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} required placeholder="e.g. 3101 (Creates Device_3101)" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Machine Name</label>
        <input style={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="e.g. ROV-Alpha" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Model</label>
        <input style={styles.input} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} required placeholder="e.g. EX-3000" />
      </div>
      <div style={styles.field}>
        <label style={styles.label}>Status</label>
        <select style={styles.input} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as "online" | "offline" | "maintenance" })}>
          <option value="online">Online</option>
          <option value="offline">Offline</option>
          <option value="maintenance">Maintenance</option>
        </select>
      </div>
      <div style={styles.formActions}>
        <button type="button" style={styles.cancelBtn} onClick={onClose}>Cancel</button>
        <button type="submit" style={styles.submitBtn}>Create Device</button>
      </div>
    </form>
  );
};

// ─── Home Page ────────────────────────────────────────────────────────────────
const BASE_URL = "http://localhost:8000"; 

const Home: React.FC = () => {
  const [users, setUsers] = useState<Employee[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddUser, setShowAddUser] = useState(false);
  const [showAddMachine, setShowAddMachine] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${BASE_URL}/users`).then(r => r.json()),
      fetch(`${BASE_URL}/machines`).then(r => r.json())
    ]).then(([u, m]) => {
      if (Array.isArray(u)) setUsers(u);
      if (Array.isArray(m)) setMachines(m);
    }).catch(err => console.error("Backend offline", err))
      .finally(() => setLoading(false));
  }, []);

  const handleAddUser = async (user: any) => {
    try {
      const res = await fetch(`${BASE_URL}/users`, {
        method: "POST", 
        headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify(user)
      });
      if (res.ok) {
        const newUser = await res.json();
        setUsers(prev => [...prev, newUser]);
        setShowAddUser(false);
      } else {
        const err = await res.json();
        alert(`❌ Database Error:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error:\nCould not reach the backend API.`); }
  };

  const handleAddMachine = async (machine: any) => {
    try {
      const res = await fetch(`${BASE_URL}/machines`, {
        method: "POST", 
        headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify(machine)
      });
      if (res.ok) {
        const newMachine = await res.json();
        setMachines(prev => [...prev, newMachine]);
        setShowAddMachine(false);
      } else {
        const err = await res.json();
        alert(`❌ Database Error:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error:\nCould not reach the backend API.`); }
  };

  // ─── DELETE FUNCTIONS ───
  const handleDeleteUser = async (id: string, username: string) => {
    if (!window.confirm(`Are you sure you want to permanently delete Employee: ${username}?`)) return;
    try {
      const res = await fetch(`${BASE_URL}/users/${id}`, { method: "DELETE" });
      if (res.ok) {
        setUsers(users.filter(u => u.id !== id));
      } else {
        const err = await res.json();
        alert(`❌ Failed to delete:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error:\nCould not reach the backend API.`); }
  };

  const handleDeleteMachine = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete Device: ${name}?\nWARNING: This will drop the 'Device_${id}' table and all its data permanently.`)) return;
    try {
      const res = await fetch(`${BASE_URL}/machines/${id}`, { method: "DELETE" });
      if (res.ok) {
        setMachines(machines.filter(m => m.id !== id));
      } else {
        const err = await res.json();
        alert(`❌ Failed to delete:\n${err.detail}`);
      }
    } catch (e) { alert(`❌ Server Error:\nCould not reach the backend API.`); }
  };

  const statusBadge = (text: string, type: "good" | "bad" | "warn") => {
    const colors = { good: "#22c55e", bad: "#ef4444", warn: "#f59e0b" };
    const color = colors[type];
    return (
      <span style={{ ...styles.badge, background: `${color}22`, color: color, border: `1px solid ${color}55` }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, display: "inline-block", marginRight: 5 }} />
        {text.toUpperCase()}
      </span>
    );
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.logo}><span style={styles.logoAccent}>EVOX</span><span style={styles.logoLight}>AI</span></div>
        <div style={styles.headerRight}><span style={styles.headerLabel}>Dashboard</span></div>
      </header>

      <main style={styles.main}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 36 }}>
          <div>
            <h1 style={styles.pageTitle}>Management Console</h1>
            <p style={{...styles.pageSubtitle, marginBottom: 0}}>{loading ? "Loading data…" : `${users.length} Employees · ${machines.length} Devices`}</p>
          </div>
          
          <button 
            onClick={() => window.location.reload()} 
            style={{...styles.cancelBtn, border: "1px solid rgba(56,189,248,0.5)", color: "#38bdf8", padding: "8px 16px"}}
          >
            ↻ Refresh Data
          </button>
        </div>

        {loading ? (
          <div style={styles.loader}><div style={styles.spinner} /></div>
        ) : (
          <div style={styles.grid}>
            
            {/* ── Employees Table ── */}
            <section style={styles.card}>
              <div style={styles.cardHeader}>
                <div><h2 style={styles.cardTitle}>Employees</h2></div>
                <button style={styles.addBtn} onClick={() => setShowAddUser(true)}>+ Add Employee</button>
              </div>
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={{...styles.th, width: "15%"}}>ID</th>
                      <th style={{...styles.th, width: "25%"}}>Username</th>
                      <th style={{...styles.th, width: "25%"}}>Devices</th>
                      <th style={{...styles.th, width: "20%"}}>Role</th>
                      <th style={{...styles.th, width: "15%", textAlign: "center"}}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u, i) => (
                      <tr key={u.id} style={{ ...styles.tr, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
                        <td style={styles.td}><span style={styles.idPill}>#{u.id}</span></td>
                        <td style={{ ...styles.td, fontWeight: 600 }}>
                          <div style={styles.truncate}>{u.user_name}</div>
                        </td>
                        <td style={{...styles.td, color: "#94a3b8"}}>
                          <div style={styles.truncate}>{u.devices_assigned || "—"}</div>
                        </td>
                        <td style={styles.td}>{statusBadge(u.role_commend, u.role_commend === "manager" ? "warn" : "good")}</td>
                        <td style={{...styles.td, textAlign: "center"}}>
                          <button style={styles.deleteBtn} onClick={() => handleDeleteUser(u.id, u.user_name)}>
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && <tr><td colSpan={5} style={styles.empty}>No employees yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            {/* ── Machines Table ── */}
            <section style={styles.card}>
              <div style={styles.cardHeader}>
                <div><h2 style={styles.cardTitle}>Devices</h2></div>
                <button style={styles.addBtn} onClick={() => setShowAddMachine(true)}>+ Add Device</button>
              </div>
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={{...styles.th, width: "15%"}}>ID</th>
                      <th style={{...styles.th, width: "25%"}}>Name</th>
                      <th style={{...styles.th, width: "25%"}}>Model</th>
                      <th style={{...styles.th, width: "20%"}}>Status</th>
                      <th style={{...styles.th, width: "15%", textAlign: "center"}}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {machines.map((m, i) => (
                      <tr key={m.id} style={{ ...styles.tr, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
                        <td style={styles.td}><span style={styles.idPill}>#{m.id}</span></td>
                        <td style={{ ...styles.td, fontWeight: 600 }}>
                           <div style={styles.truncate}>{m.name}</div>
                        </td>
                        <td style={{ ...styles.td, color: "#94a3b8" }}>
                           <div style={styles.truncate}>{m.model}</div>
                        </td>
                        <td style={styles.td}>{statusBadge(m.status, m.status === "online" ? "good" : m.status === "offline" ? "bad" : "warn")}</td>
                        <td style={{...styles.td, textAlign: "center"}}>
                          <button style={styles.deleteBtn} onClick={() => handleDeleteMachine(m.id, m.name)}>
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {machines.length === 0 && <tr><td colSpan={5} style={styles.empty}>No devices yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

          </div>
        )}
      </main>

      {/* ── Modals ── */}
      {showAddUser && (
        <Modal title="Add New Employee" onClose={() => setShowAddUser(false)}>
          <AddUserForm onClose={() => setShowAddUser(false)} onAdd={handleAddUser} />
        </Modal>
      )}
      {showAddMachine && (
        <Modal title="Create New Device Table" onClose={() => setShowAddMachine(false)}>
          <AddMachineForm onClose={() => setShowAddMachine(false)} onAdd={handleAddMachine} />
        </Modal>
      )}
    </div>
  );
};

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#0a0e1a", color: "#e2e8f0", fontFamily: "'DM Sans', 'Segoe UI', sans-serif" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 40px", borderBottom: "1px solid rgba(255,255,255,0.07)", background: "rgba(255,255,255,0.03)", backdropFilter: "blur(10px)" },
  logo: { fontSize: 22, fontWeight: 800, letterSpacing: 1.5 },
  logoAccent: { color: "#38bdf8" }, logoLight: { color: "#e2e8f0" },
  headerLabel: { fontSize: 12, color: "#64748b", letterSpacing: 2, textTransform: "uppercase" },
  main: { maxWidth: 1400, margin: "0 auto", padding: "40px 32px" },
  pageTitle: { fontSize: 28, fontWeight: 700, marginBottom: 4, color: "#f1f5f9" },
  pageSubtitle: { fontSize: 14, color: "#64748b", marginBottom: 36 },
  loader: { display: "flex", justifyContent: "center", padding: "80px 0" },
  spinner: { width: 36, height: 36, border: "3px solid rgba(56,189,248,0.15)", borderTop: "3px solid #38bdf8", borderRadius: "50%", animation: "spin 0.8s linear infinite" },
  
  // ── GRID & CARD FIXES ──
  grid: { 
    display: "grid", 
    gridTemplateColumns: "1fr 1fr", 
    gap: 28,
    alignItems: "start" 
  },
  card: { 
    background: "rgba(255,255,255,0.04)", 
    border: "1px solid rgba(255,255,255,0.08)", 
    borderRadius: 16, 
    overflow: "hidden",
    display: "flex",
    flexDirection: "column"
  },
  cardHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.07)" },
  cardTitle: { fontSize: 16, fontWeight: 700, color: "#f1f5f9", margin: 0 },
  addBtn: { padding: "8px 18px", background: "linear-gradient(135deg, #0ea5e9, #38bdf8)", border: "none", borderRadius: 8, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "0.2s" },
  
  // ── TABLE SYMMETRY FIXES ──
  tableWrapper: { 
    overflowX: "auto",
    maxHeight: "600px", 
    overflowY: "auto"
  },
  table: { 
    width: "100%", 
    borderCollapse: "collapse", 
    fontSize: 13,
    tableLayout: "fixed" 
  },
  th: { padding: "12px 16px", textAlign: "left", color: "#64748b", fontWeight: 600, textTransform: "uppercase", fontSize: 11, borderBottom: "1px solid rgba(255,255,255,0.07)" },
  tr: { transition: "background 0.1s" },
  td: { padding: "13px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", verticalAlign: "middle" },
  
  // ── TRUNCATION & BUTTONS ──
  truncate: {
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: "100%"
  },
  deleteBtn: {
    background: "rgba(239, 68, 68, 0.1)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    color: "#ef4444",
    padding: "5px 10px",
    borderRadius: "6px",
    fontSize: "11px",
    fontWeight: "bold",
    cursor: "pointer",
    textTransform: "uppercase"
  },
  
  idPill: { background: "rgba(56,189,248,0.1)", color: "#38bdf8", padding: "2px 8px", borderRadius: 99, fontSize: 12, fontWeight: 700 },
  badge: { padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 600, display: "inline-flex", alignItems: "center" },
  empty: { textAlign: "center", color: "#64748b", padding: "30px", fontStyle: "italic" },
  
  // ── MODALS ──
  overlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, backdropFilter: "blur(4px)" },
  modal: { background: "#111827", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, width: "100%", maxWidth: 460, boxShadow: "0 25px 60px rgba(0,0,0,0.5)" },
  modalHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.08)" },
  modalTitle: { fontSize: 16, fontWeight: 700, color: "#f1f5f9" },
  closeBtn: { background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 16 },
  modalBody: { padding: "24px" },
  form: { display: "flex", flexDirection: "column", gap: 18 },
  field: { display: "flex", flexDirection: "column", gap: 6 },
  label: { fontSize: 12, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase" },
  input: { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#e2e8f0", fontSize: 14, outline: "none" },
  formActions: { display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 },
  cancelBtn: { padding: "9px 20px", background: "transparent", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, color: "#94a3b8", cursor: "pointer", fontSize: 13 },
  submitBtn: { padding: "9px 20px", background: "linear-gradient(135deg, #0ea5e9, #38bdf8)", border: "none", borderRadius: 8, color: "#fff", fontWeight: 600, cursor: "pointer", fontSize: 13 },
};

export default Home;