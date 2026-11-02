const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, headers, ...rest } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type UserRole = "admin" | "accountant" | "viewer";
export type VatFrequency = "monthly" | "quarterly" | "annual";
export type VatPeriodStatus = "open" | "filed" | "paid";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface Company {
  id: number;
  name: string;
  kvk_number: string | null;
  vat_number: string | null;
  address: string | null;
  vat_frequency: VatFrequency;
}

export interface VatPeriod {
  id: number;
  label: string;
  start_date: string;
  end_date: string;
  filing_deadline: string;
  payment_deadline: string;
  status: VatPeriodStatus;
}

export interface FinancialYear {
  id: number;
  year: number;
  start_date: string;
  end_date: string;
  vat_periods: VatPeriod[];
}

export interface DashboardSummary {
  company_count: number;
  open_vat_periods: number;
  upcoming_deadlines: {
    company_id: number;
    company_name: string;
    period_label: string;
    filing_deadline: string;
    payment_deadline: string;
  }[];
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: (token: string) => request<User>("/auth/me", { token }),
  listCompanies: (token: string) => request<Company[]>("/companies", { token }),
  createCompany: (
    token: string,
    payload: Pick<Company, "name" | "kvk_number" | "vat_number" | "address" | "vat_frequency">
  ) =>
    request<Company>("/companies", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  getCompany: (token: string, id: number) => request<Company>(`/companies/${id}`, { token }),
  listFinancialYears: (token: string, companyId: number) =>
    request<FinancialYear[]>(`/companies/${companyId}/financial-years`, { token }),
  createFinancialYear: (token: string, companyId: number, year: number) =>
    request<FinancialYear>(`/companies/${companyId}/financial-years`, {
      method: "POST",
      token,
      body: JSON.stringify({ year }),
    }),
  dashboard: (token: string) => request<DashboardSummary>("/dashboard", { token }),
};
