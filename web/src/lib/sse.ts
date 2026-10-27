// Incremental Server-Sent Events parser for a fetch() body: feed it decoded text in any chunking,
// get complete messages back. Handles CRLF, comment lines and multi-line data fields.

export interface SseMessage {
  event: string;
  data: string;
}

export function createSseParser() {
  let buffer = "";
  return {
    push(text: string): SseMessage[] {
      buffer += text.replace(/\r\n?/g, "\n");
      const out: SseMessage[] = [];
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split("\n")) {
          if (line === "" || line.startsWith(":")) continue;
          const colon = line.indexOf(":");
          const field = colon === -1 ? line : line.slice(0, colon);
          const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
          if (field === "event") event = value;
          else if (field === "data") data.push(value);
        }
        if (data.length) out.push({ event, data: data.join("\n") });
      }
      return out;
    },
  };
}
