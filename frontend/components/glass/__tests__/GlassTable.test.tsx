import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GlassTable from "../GlassTable";
import { expectNoAxeViolations } from "../../../test/axe";

interface Row {
  id: number;
  name: string;
}

const ROWS: Row[] = [
  { id: 1, name: "Alpha" },
  { id: 2, name: "Beta" },
];

const COLUMNS = [{ key: "name", header: "Name", render: (r: Row) => r.name }];

describe("GlassTable", () => {
  it("renders an empty message when there are no rows", () => {
    render(<GlassTable columns={COLUMNS} rows={[]} rowKey={(r) => r.id} emptyMessage="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders column headers and row values (both the desktop table and the CSS-only mobile stacked view)", () => {
    render(<GlassTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    // GlassTable renders two layouts simultaneously and toggles visibility
    // via CSS (hidden sm:table / sm:hidden), so each value legitimately
    // appears twice in the DOM -- getAllByText, not getByText.
    expect(screen.getAllByText("Name").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Alpha")).toHaveLength(2);
    expect(screen.getAllByText("Beta")).toHaveLength(2);
  });

  it("clickable rows are reachable by keyboard and activate on Enter/Space", () => {
    const onRowClick = vi.fn();
    render(<GlassTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} onRowClick={onRowClick} />);
    const rows = screen.getAllByRole("button");
    // Desktop <tr> and mobile stacked-card view both render a role="button"
    // row per data row -- the first one is the desktop table's first row.
    const firstRow = rows[0];
    expect(firstRow).toHaveAttribute("tabIndex", "0");

    fireEvent.keyDown(firstRow, { key: "Enter" });
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);

    fireEvent.keyDown(firstRow, { key: " " });
    expect(onRowClick).toHaveBeenCalledTimes(2);
  });

  it("non-clickable rows (no onRowClick) are not given button semantics", () => {
    render(<GlassTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("has no axe violations when rows are clickable", async () => {
    const { container } = render(<GlassTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} onRowClick={vi.fn()} />);
    await expectNoAxeViolations(container);
  });
});
