import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GlassDropdown from "../GlassDropdown";
import { expectNoAxeViolations } from "../../../test/axe";

function renderMenu() {
  return render(
    <GlassDropdown label="Actions">
      {(close) => (
        <>
          <button role="menuitem" onClick={close}>
            First
          </button>
          <button role="menuitem" onClick={close}>
            Second
          </button>
          <button role="menuitem" onClick={close}>
            Third
          </button>
        </>
      )}
    </GlassDropdown>
  );
}

describe("GlassDropdown", () => {
  it("opens the menu and moves focus to the first item", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "First" }));
  });

  it("ArrowDown/ArrowUp cycle between menu items, wrapping at the ends", () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    const first = screen.getByRole("menuitem", { name: "First" });
    const second = screen.getByRole("menuitem", { name: "Second" });
    const third = screen.getByRole("menuitem", { name: "Third" });

    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(third);
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(first); // wraps

    fireEvent.keyDown(document, { key: "ArrowUp" });
    expect(document.activeElement).toBe(third); // wraps backward
  });

  it("Escape closes the menu and returns focus to the trigger", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: "Actions" });
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("clicking a menu item's close() returns focus to the trigger", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: "Actions" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Second" }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("has no axe violations when open", async () => {
    const { container } = renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    await expectNoAxeViolations(container);
  });
});
