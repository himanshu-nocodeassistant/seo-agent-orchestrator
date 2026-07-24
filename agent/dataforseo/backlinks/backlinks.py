from agent.dataforseo.client import DataForSEOClient


class BacklinksAPI(DataForSEOClient):

    def summary_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/summary/live

        Returns an aggregated backlink profile summary for a target
        (domain, subdomain, or URL): total backlinks, referring domains,
        rank, spam score, and top anchors/pages/countries.

        Each task dict may contain:
            target                    (str, required)  domain, subdomain, or URL
            include_subdomains          (bool)  default True
            include_indirect_links       (bool)  default True
            exclude_internal_backlinks   (bool)  default True
            internal_list_limit          (int)   max items in internal lists, default 10
            backlinks_status_type        (str)   "all" (default), "live", "lost"
            backlinks_filters            (list)
            tag                          (str)

        Result dict contains:
            target, first_seen, lost_date, rank, backlinks, backlinks_spam_score,
            crawled_pages, info (target metadata), referring_domains,
            referring_domains_nofollow, referring_main_domains,
            referring_ips, referring_subnets, referring_pages,
            referring_links_tld, referring_links_types,
            referring_links_attributes, referring_links_platform_types,
            referring_links_semantic_locations, referring_links_countries
        """
        data = self._post("backlinks/summary/live", tasks)
        return self._extract_results(data)

    def backlinks_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/backlinks/live

        Returns individual backlinks pointing to a target, with anchor
        text, link attributes, and referring page/domain metrics.

        Each task dict may contain:
            target                     (str, required)  domain, subdomain, or URL
            mode                        (str)  "as_is" (default), "one_per_domain",
                                                "one_per_anchor"
            filters                    (list)
            order_by                   (list[str])
            limit                      (int)   max 1000, default 100
            offset                     (int)
            backlinks_status_type       (str)   "all" (default), "live", "lost"
            include_subdomains          (bool)  default True
            include_indirect_links      (bool)  default True
            exclude_internal_backlinks  (bool)  default True
            tag                         (str)

        Result dict contains:
            target, total_count, items_count,
            items [{type, domain_from, url_from, url_to, anchor, dofollow,
                     rank, page_from_rank, is_new, is_lost, ...}]
        """
        data = self._post("backlinks/backlinks/live", tasks)
        return self._extract_results(data)

    def anchors_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/anchors/live

        Returns anchor texts used in backlinks pointing to a target,
        aggregated with backlink and referring domain counts per anchor.

        Each task dict may contain:
            target                     (str, required)  domain, subdomain, or URL
            filters                    (list)
            order_by                   (list[str])
            limit                      (int)   max 1000, default 100
            offset                     (int)
            internal_list_limit         (int)
            backlinks_status_type       (str)   "all" (default), "live", "lost"
            include_subdomains          (bool)  default True
            include_indirect_links      (bool)  default True
            exclude_internal_backlinks  (bool)  default True
            tag                         (str)

        Result dict contains:
            target, total_count, items_count,
            items [{anchor, rank, backlinks, first_seen, ...referring domain counts}]
        """
        data = self._post("backlinks/anchors/live", tasks)
        return self._extract_results(data)

    def domain_pages_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/domain_pages/live

        Returns pages of a target domain along with their backlink
        profile summary (backlinks, referring domains, rank per page).

        Each task dict may contain:
            target                     (str, required)  domain
            filters                    (list)
            order_by                   (list[str])
            limit                      (int)   max 1000, default 100
            offset                     (int)
            internal_list_limit         (int)
            backlinks_status_type       (str)   "all" (default), "live", "lost"
            include_subdomains          (bool)  default True
            tag                         (str)

        Result dict contains:
            target, total_count, items_count,
            items [{page, page_summary: {backlinks, referring_domains, rank, ...}}]
        """
        data = self._post("backlinks/domain_pages/live", tasks)
        return self._extract_results(data)

    def referring_domains_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/referring_domains/live

        Returns domains that link to a target, with backlink counts,
        rank, and other referring-domain-level metrics.

        Each task dict may contain:
            target                       (str, required)  domain, subdomain, or URL
            filters                      (list)
            order_by                     (list[str])
            limit                        (int)   max 1000, default 100
            offset                       (int)
            backlinks_status_type         (str)   "all" (default), "live", "lost"
            backlinks_filters             (list)
            include_subdomains            (bool)  default True
            include_indirect_links        (bool)  default True
            exclude_internal_backlinks    (bool)  default True
            tag                           (str)

        Result dict contains:
            target, total_count, items_count,
            items [{domain, rank, backlinks, first_seen, backlinks_spam_score, ...}]
        """
        data = self._post("backlinks/referring_domains/live", tasks)
        return self._extract_results(data)

    def referring_networks_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/referring_networks/live

        Returns IP addresses/subnets that host referring domains linking
        to a target — useful for detecting link networks (PBNs).

        Each task dict may contain:
            target                       (str, required)  domain, subdomain, or URL
            network_address_type          (str)  "ip" or "subnet" (default)
            filters                       (list)
            order_by                      (list[str])
            limit                         (int)   max 1000, default 100
            offset                        (int)
            backlinks_status_type          (str)   "all" (default), "live", "lost"
            backlinks_filters              (list)
            include_subdomains             (bool)  default True
            include_indirect_links         (bool)  default True
            exclude_internal_backlinks     (bool)  default True
            tag                            (str)

        Result dict contains:
            target, total_count, items_count,
            items [{network_address, rank, backlinks, referring_domains, ...}]
        """
        data = self._post("backlinks/referring_networks/live", tasks)
        return self._extract_results(data)

    def domain_intersection_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/domain_intersection/live

        Compares the backlink profiles of multiple target domains and
        returns referring domains that link to some or all of them —
        useful for finding shared/competitor link sources.

        Each task dict may contain:
            targets                    (dict, required)  {"1": "domain1.com", "2": "domain2.com", ...}
                                                            up to 20 targets
            exclude_targets             (list[str])  domains to exclude from results
            include_subdomains          (bool)  default True
            include_indirect_links      (bool)  default True
            exclude_internal_backlinks  (bool)  default True
            filters                     (list)
            order_by                    (list[str])
            limit                       (int)   max 1000, default 100
            offset                      (int)
            tag                         (str)

        Result dict contains:
            total_count, items_count,
            items [{domain_1_rank... , intersection_result: {"1": {...}, "2": {...}}}]
        """
        data = self._post("backlinks/domain_intersection/live", tasks)
        return self._extract_results(data)

    def competitors_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/competitors/live

        Returns domains with a similar backlink profile / referring
        domain overlap to the target — useful for finding link-building
        competitors.

        Each task dict may contain:
            target                    (str, required)  domain
            filters                   (list)
            order_by                  (list[str])
            limit                     (int)   max 1000, default 100
            offset                    (int)
            exclude_large_domains      (bool)  default True
            tag                       (str)

        Result dict contains:
            target, total_count, items_count,
            items [{target, rank, intersections, ...backlink metrics}]
        """
        data = self._post("backlinks/competitors/live", tasks)
        return self._extract_results(data)

    def bulk_ranks_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/bulk_ranks/live

        Returns DataForSEO Rank for up to 1000 targets (domains,
        subdomains, or URLs) in a single request.

        Each task dict may contain:
            targets                  (list[str], required)  max 1000
            tag                      (str)

        Result dict contains:
            total_count, items_count, items [{target, rank}]
        """
        data = self._post("backlinks/bulk_ranks/live", tasks)
        return self._extract_results(data)

    def bulk_referring_domains_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /backlinks/bulk_referring_domains/live

        Returns referring domains count for up to 1000 targets in a
        single request.

        Each task dict may contain:
            targets                  (list[str], required)  max 1000
            tag                      (str)

        Result dict contains:
            total_count, items_count, items [{target, referring_domains}]
        """
        data = self._post("backlinks/bulk_referring_domains/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
