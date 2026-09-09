import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#2f8f72",
          color: "#f4f6f5",
          fontSize: 118,
          fontWeight: 700,
          letterSpacing: "-6px",
        }}
      >
        A
      </div>
    ),
    { ...size },
  );
}
