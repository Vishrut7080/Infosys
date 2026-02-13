import { useState } from "react";
import { listenText } from "../Audio/speech_to_text";
import { speakText } from "../Audio/text_to_speech";

export default function VoiceLoginPage() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();
        // Replace with your backend login logic
        console.log("Logging in with:", email, password);
        await speakText("Login successful!"); // optional TTS feedback
    };

    const handleVoiceLogin = async () => {
        setLoading(true);
        try {
            await speakText("Please say your email address.");
            const spokenEmail = await listenText();
            setEmail(spokenEmail);
            console.log("Captured Email:", spokenEmail);

            await speakText("Please say your password.");
            const spokenPassword = await listenText();
            setPassword(spokenPassword);
            console.log("Captured Password:", spokenPassword);

            await handleLogin({ preventDefault: () => { } });
        } catch (error) {
            console.error("Voice login failed:", error);
            await speakText("Sorry, I could not capture your credentials. Please try again.");
        }
        setLoading(false);
    };

    return (
        <div className="flex items-center justify-center min-h-screen bg-gray-100">
            <div className="w-full max-w-md p-8 bg-white shadow-lg rounded-lg">
                <h2 className="text-2xl font-bold text-center mb-6">Voice Assistant Login</h2>

                <form onSubmit={handleLogin} className="space-y-4">
                    <input
                        type="email"
                        placeholder="Enter your email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full p-3 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                        required
                    />

                    <div className="relative">
                        <input
                            type={showPassword ? "text" : "password"}
                            placeholder="Enter your password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full p-3 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                            required
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="absolute right-3 top-3 text-gray-500"
                        >
                            {showPassword ? "🙈" : "👁️"}
                        </button>
                    </div>

                    <button
                        type="submit"
                        className="w-full bg-blue-600 text-white p-3 rounded font-semibold hover:bg-blue-700 transition"
                    >
                        Login
                    </button>
                </form>

                <div className="flex justify-between mt-4 text-sm text-blue-600">
                    <a href="#">Forgot Password?</a>
                    <a href="#">Sign Up</a>
                </div>

                <div className="mt-6 text-center">
                    <button
                        onClick={handleVoiceLogin}
                        disabled={loading}
                        className={`flex items-center justify-center w-full p-3 border rounded hover:bg-gray-100 transition ${loading ? "opacity-50 cursor-not-allowed" : ""
                            }`}
                    >
                        <span className="mr-2">🎤</span> {loading ? "Listening..." : "Login via Voice"}
                    </button>
                </div>
            </div>
        </div>
    );
}
