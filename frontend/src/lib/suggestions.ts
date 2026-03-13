import api from "@/lib/api"

type SuggestionsPage = {
  items: any[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  next_offset: number | null
}

export async function fetchAllSuggestions(appId: number, pageSize = 200): Promise<any[]> {
  const all: any[] = []
  let offset = 0

  // Safety ceiling to prevent accidental infinite loops.
  for (let page = 0; page < 100; page += 1) {
    const response = await api.get(`/api/v1/apps/${appId}/suggestions`, {
      params: {
        paginated: true,
        limit: pageSize,
        offset,
      },
    })
    const data = response.data as SuggestionsPage | any[]

    // Backward compatibility if paginated mode is not available.
    if (Array.isArray(data)) {
      return data
    }

    all.push(...(data.items || []))

    if (!data.has_more || data.next_offset === null || data.next_offset === undefined) {
      break
    }
    offset = data.next_offset
  }

  return all
}
