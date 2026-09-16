import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDuration, formatINR } from "../../lib/format.js";
import { useQueryParams } from "../../lib/hooks.js";

const PAGE_SIZE = 20;

export default function AdminWebinars() {
  const queryClient = useQueryClient();
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const departments = useQuery({ queryKey: ["admin", "departments"], queryFn: () => api("/admin/departments") });
  const webinars = useQuery({
    queryKey: ["admin", "webinars", params],
    queryFn: () =>
      api("/admin/webinars", { query: { status: params.status, department_id: params.department_id, q: params.q, page, page_size: PAGE_SIZE } }),
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }) => api(`/admin/webinars/${id}`, { method: "PUT", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "webinars"] }),
  });

  return (
    <>
      <PageHeader title="Webinars" subtitle="Courses, prices and their bookable slots." actions={<Button to="/admin/webinars/new">New webinar</Button>} />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_12rem_14rem_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search title" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Status" value={params.status ?? ""} onChange={(e) => setParams({ status: e.target.value })}>
          <option value="">All</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </Select>
        <Select label="Department" value={params.department_id ?? ""} onChange={(e) => setParams({ department_id: e.target.value })}>
          <option value="">All</option>
          {(departments.data ?? []).map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </Select>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      <QueryState query={webinars}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No webinars" action={<Button to="/admin/webinars/new">Create the first webinar</Button>} />
          ) : (
            <>
              <Table headers={["Title", "Departments", "Price", "Duration", "Status", ""]}>
                {data.items.map((webinar) => (
                  <tr key={webinar.id}>
                    <Td className="font-medium text-slate-900">
                      {webinar.title}
                      {webinar.instructor && <p className="text-xs font-normal text-slate-500">{webinar.instructor}</p>}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        {webinar.departments.map((department) => (
                          <Badge key={department.id}>{department.name}</Badge>
                        ))}
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap">{formatINR(webinar.price_paise)}</Td>
                    <Td className="whitespace-nowrap">{formatDuration(webinar.duration_minutes)}</Td>
                    <Td>
                      <StatusBadge status={webinar.status} />
                    </Td>
                    <Td className="whitespace-nowrap">
                      <div className="flex justify-end gap-2">
                        <Button size="sm" to={`/admin/webinars/${webinar.id}/slots`}>
                          Slots
                        </Button>
                        <Button size="sm" variant="secondary" to={`/admin/webinars/${webinar.id}/edit`}>
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const status = webinar.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
                            if (status === "ACTIVE" || window.confirm(`Deactivate "${webinar.title}"? It will be hidden from the catalog; existing bookings stay valid.`)) {
                              setStatus.mutate({ id: webinar.id, status });
                            }
                          }}
                        >
                          {webinar.status === "ACTIVE" ? "Deactivate" : "Activate"}
                        </Button>
                      </div>
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
