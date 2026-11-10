import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GlassButton from "../GlassButton";
import { expectNoAxeViolations } from "../../../test/axe";

describe("GlassButton", () => {
  it("renders each variant with its own class and no axe violations", async () => {
    const variants = ["primary", "secondary", "outline", "ghost", "danger", "success"] as const;
    for (const variant of variants) {
      const { container, unmount } = render(<GlassButton variant={variant}>Click me</GlassButton>);
      const button = screen.getByRole("button", { name: "Click me" });
      expect(button.className).toContain(
        { primary: "btn-primary-v2", secondary: "btn-secondary-v2", outline: "btn-outline-v2", ghost: "btn-ghost-v2", danger: "btn-danger-v2", success: "btn-success-v2" }[variant]
      );
      await expectNoAxeViolations(container);
      unmount();
    }
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<GlassButton onClick={onClick}>Save</GlassButton>);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disables the button and does not fire onClick when disabled", () => {
    const onClick = vi.fn();
    render(
      <GlassButton onClick={onClick} disabled>
        Save
      </GlassButton>
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("loading state disables the button, sets aria-busy, and shows a spinner", () => {
    render(<GlassButton loading>Submitting</GlassButton>);
    const button = screen.getByRole("button", { name: "Submitting" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button.querySelector("svg")).not.toBeNull();
  });
});
