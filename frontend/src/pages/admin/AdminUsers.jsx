import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/AuthContext.jsx";
import { Alert, Badge, Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDate, formatINR } from "../../lib/format.js";
import { useQueryParams } from "../../lib/hooks.js";

const PAGE_SIZE = 25;

export default function AdminUsers() {
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const departments = useQuery({ queryKey: ["admin", "departments"], queryFn: () => api("/admin/departments") });
  const users = useQuery({
    queryKey: ["admin", "users", params],
    queryFn: () =>
      api("/admin/users", {
        query: { q: params.q, role: params.role, department_id: params.department_id, is_active: params.is_active, page, page_size: PAGE_SIZE },
      }),
  });
  const setActive = useMutation({
    mutationFn: ({ id, is_active }) => api(`/admin/users/${id}`, { method: "PUT", body: { is_active } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <>
      <PageHeader title="Users" subtitle="Registered learners and admins." />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_10rem_14rem_10rem_auto] lg:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search" placeholder="Name, email or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Role" value={params.role ?? ""} onChange={(e) => setParams({ role: e.target.value })}>
          <option value="">All</option>
          <option value="USER">Learners</option>
          <option value="ADMIN">Admins</option>
        </Select>
        <Select label="Department" value={params.department_id ?? ""} onChange={(e) => setParams({ department_id: e.target.value })}>
          <option value="">All</option>
          {(departments.data ?? []).map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </Select>
        <Select label="Account" value={params.is_active ?? ""} onChange={(e) => setParams({ is_active: e.target.value })}>
          <option value="">All</option>
          <option value="true">Active</option>
          <option value="false">Deactivated</option>
        </Select>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {setActive.isError && (
        <Alert kind="error" className="mb-4">
          {setActive.error.message}
        </Alert>
      )}
      <QueryState query={users}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No users match these filters" />
          ) : (
            <>
              <Table headers={["User", "Role", "Department", "Bookings", "Paid", "Joined", "Account", ""]}>
                {data.items.map((user) => (
                  <tr key={user.id}>
                    <Td>
                      <p className="font-medium text-slate-900">{user.name}</p>
                      <p className="text-xs text-slate-500">{user.email}</p>
                      <p className="text-xs text-slate-500">{user.phone}</p>
                    </Td>
                    <Td>
                      <Badge color={user.role === "ADMIN" ? "brand" : "slate"}>{user.role === "ADMIN" ? "Admin" : "Learner"}</Badge>
                    </Td>
                    <Td>{user.department?.name ?? "—"}</Td>
                    <Td className="whitespace-nowrap">
                      <Link to={`/admin/bookings?user_id=${user.id}`} className="text-brand-700 hover:underline">
                        {user.bookings_count} total
                      </Link>
                      <p className="text-xs text-slate-500">{user.confirmed_bookings_count} confirmed</p>
                    </Td>
                    <Td className="whitespace-nowrap">
                      <Link to={`/admin/payments?user_id=${user.id}`} className="text-brand-700 hover:underline">
                        {user.total_paid_paise ? formatINR(user.total_paid_paise) : "₹0"}
                      </Link>
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{formatDate(user.created_at)}</Td>
                    <Td>
                      <Badge color={user.is_active ? "green" : "slate"}>{user.is_active ? "Active" : "Deactivated"}</Badge>
                    </Td>
                    <Td className="text-right">
                      {user.id !== me.id && (
                        <Button
                          size="sm"
                          variant={user.is_active ? "ghost" : "secondary"}
                          loading={setActive.isPending && setActive.variables?.id === user.id}
                          onClick={() => {
                            if (!user.is_active || window.confirm(`Deactivate ${user.name}? They'll be signed out and can't log in. Bookings are kept.`)) {
                              setActive.mutate({ id: user.id, is_active: !user.is_active });
                            }
                          }}
                        >
                          {user.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(next) => setParams({ page: next })} />
            </>
          )
        }
      </QueryState>
    </>
  );
}
