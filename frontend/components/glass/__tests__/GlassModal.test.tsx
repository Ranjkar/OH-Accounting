import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useState } from "react";
import GlassModal from "../GlassModal";
import { expectNoAxeViolations } from "../../../test/axe";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open dialog</button>
      <GlassModal open={open} onClose={() => setOpen(false)} title="Confirm action">
        <button>First field</button>
        <button>Last field</button>
      </GlassModal>
    </div>
  );
}

describe("GlassModal", () => {
  it("is absent from the DOM when closed, and has dialog semantics when open", () => {
    render(
      <GlassModal open={false} onClose={vi.fn()} title="Hidden">
        content
      </GlassModal>
    );
    expect(screen.queryByRole("dialog")).toBeNull();

    render(
      <GlassModal open={true} onClose={vi.fn()} title="Visible">
        content
      </GlassModal>
    );
    expect(screen.getByRole("dialog", { name: "Visible" })).toBeInTheDocument();
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(
      <GlassModal open={true} onClose={onClose} title="Visible">
        content
      </GlassModal>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <GlassModal open={true} onClose={onClose} title="Visible">
        content
      </GlassModal>
    );
    const backdrop = container.querySelector('[aria-hidden="true"]')!;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("returns focus to the element that opened it, after closing", () => {
    render(<Harness />);
    const openButton = screen.getByRole("button", { name: "Open dialog" });
    openButton.focus();
    fireEvent.click(openButton);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(openButton);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <GlassModal open={true} onClose={vi.fn()} title="Visible" footer={<button>Confirm</button>}>
        content
      </GlassModal>
    );
    await expectNoAxeViolations(container);
  });
});
