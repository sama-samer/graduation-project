import React from "react";
import { useNavigate } from "react-router-dom";

interface UserModel {
  username: number;
  password: number;
}

const Login = () => {
  const navigate = useNavigate();
  const [user, setUser] = React.useState<UserModel>({
    username: 123,
    password: 15841,
  });

  const hashPassword = async (password: string): Promise<string> => {
    const encoder = new TextEncoder();
    const data = encoder.encode(password);
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    try {
      // ─── SIMPLE MQTT INTEGRATION TRIGGER ───
      // This instantly sends the username and password to your FastAPI backend
      fetch("http://localhost:8000/publish_login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: user.username,
          password: user.password,
        }),
      }).catch(err => console.error("MQTT Publish failed", err));
      // ────────────────────────────────────────

      // ─── YOUR EXISTING LOGIN LOGIC ───
      const storedHashedPassword =
        "54413f66631b15f7ce8502a4c202965d2db0e11e29e9609c06c97c2006e8b19d";
      const enteredPassword = user.password.toString();
      const enteredHash = await hashPassword(enteredPassword);

      if (user.username === 123 && enteredHash === storedHashedPassword) {
        console.log("Login successful!");
        navigate("/home");
      } else {
        console.log("Invalid credentials");
        alert("Invalid username or password");
      }
    } catch (error) {
      console.error("Authentication error:", error);
      alert("Authentication failed");
    }
  };

  return (
    <>
      <div className="background">
        <div className="shape"></div>
        <div className="shape"></div>
      </div>
      <form onSubmit={handleSubmit}>
        <h3>Login Here</h3>

        <label>Username</label>
        <input
          type="number"
          placeholder="Enter username number"
          id="username"
          value={user.username}
          onChange={(e) =>
            setUser({ ...user, username: parseInt(e.target.value) })
          }
        />

        <label>Password</label>
        <input
          type="number"
          placeholder="Enter password number"
          id="password"
          value={user.password}
          onChange={(e) =>
            setUser({ ...user, password: parseInt(e.target.value) })
          }
        />

        <button>Log In</button>
      </form>
    </>
  );
};

export default Login;