// SPDX-License-Identifier: MIT
//
// Minimal xNVMe ZNS append/reset latency probe for QUASAR.
//
// This intentionally bypasses zonefs. It opens the raw ZNS namespace through
// xNVMe, resets one target zone, appends N 4KiB LBAs with Zone Append, then
// resets the zone again. The output is JSON so the Python reports can consume it.

#define _GNU_SOURCE

#include <errno.h>
#include <inttypes.h>
#include <libxnvme.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t
nsec_now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ((uint64_t)ts.tv_sec * 1000000000ULL) + (uint64_t)ts.tv_nsec;
}

static int
cmp_u64(const void *lhs, const void *rhs)
{
	uint64_t a = *(const uint64_t *)lhs;
	uint64_t b = *(const uint64_t *)rhs;

	return (a > b) - (a < b);
}

static uint64_t
percentile(uint64_t *values, uint32_t count, double pct)
{
	uint32_t idx;

	if (!count) {
		return 0;
	}
	idx = (uint32_t)ceil((pct / 100.0) * (double)count);
	if (!idx) {
		idx = 1;
	}
	if (idx > count) {
		idx = count;
	}
	return values[idx - 1];
}

static void
usage(const char *argv0)
{
	fprintf(stderr,
		"Usage: %s <device> <zone-index> <append-count>\n"
		"Example: %s /dev/nvme0n1 3 4096\n",
		argv0, argv0);
}

int
main(int argc, char **argv)
{
	const char *uri;
	uint64_t zone_index;
	uint32_t append_count;
	struct xnvme_opts opts = xnvme_opts_default();
	struct xnvme_dev *dev = NULL;
	const struct xnvme_geo *geo;
	uint32_t nsid;
	uint64_t zslba;
	uint8_t *buf = NULL;
	uint64_t *append_lat = NULL;
	uint64_t reset_before_ns = 0;
	uint64_t reset_after_ns = 0;
	uint64_t total_append_ns = 0;
	int err = 0;

	if (argc != 4) {
		usage(argv[0]);
		return 2;
	}

	uri = argv[1];
	zone_index = strtoull(argv[2], NULL, 0);
	append_count = (uint32_t)strtoul(argv[3], NULL, 0);
	if (!append_count) {
		fprintf(stderr, "append-count must be > 0\n");
		return 2;
	}

	opts.be = "linux";
	opts.admin = "nvme";
	opts.sync = "nvme";
	opts.async = "emu";
	opts.mem = "posix";

	dev = xnvme_dev_open(uri, &opts);
	if (!dev) {
		err = -errno;
		fprintf(stderr, "xnvme_dev_open failed: %d\n", err);
		goto exit;
	}

	err = xnvme_dev_derive_geo(dev);
	if (err) {
		fprintf(stderr, "xnvme_dev_derive_geo failed: %d\n", err);
		goto exit;
	}
	geo = xnvme_dev_get_geo(dev);
	if (!geo || geo->type != XNVME_GEO_ZONED) {
		fprintf(stderr, "device is not reported as zoned\n");
		err = -EINVAL;
		goto exit;
	}

	nsid = xnvme_dev_get_nsid(dev);
	zslba = zone_index * geo->nsect;
	buf = xnvme_buf_alloc(dev, geo->lba_nbytes);
	append_lat = calloc(append_count, sizeof(*append_lat));
	if (!buf || !append_lat) {
		err = -ENOMEM;
		goto exit;
	}
	memset(buf, 0x5a, geo->lba_nbytes);

	{
		struct xnvme_cmd_ctx ctx = xnvme_cmd_ctx_from_dev(dev);
		uint64_t t0 = nsec_now();

		err = xnvme_znd_mgmt_send(&ctx, nsid, zslba, false,
					  XNVME_SPEC_ZND_CMD_MGMT_SEND_RESET, 0x0, NULL);
		reset_before_ns = nsec_now() - t0;
		if (err || xnvme_cmd_ctx_cpl_status(&ctx)) {
			fprintf(stderr, "zone reset before append failed: err=%d status=%d\n", err,
				xnvme_cmd_ctx_cpl_status(&ctx));
			err = err ? err : -EIO;
			goto exit;
		}
	}

	for (uint32_t idx = 0; idx < append_count; ++idx) {
		struct xnvme_cmd_ctx ctx = xnvme_cmd_ctx_from_dev(dev);
		uint64_t t0 = nsec_now();

		memcpy(buf, &idx, sizeof(idx));
		err = xnvme_znd_append(&ctx, nsid, zslba, 0, buf, NULL);
		append_lat[idx] = nsec_now() - t0;
		total_append_ns += append_lat[idx];
		if (err || xnvme_cmd_ctx_cpl_status(&ctx)) {
			fprintf(stderr, "zone append failed at idx=%u err=%d status=%d\n", idx, err,
				xnvme_cmd_ctx_cpl_status(&ctx));
			err = err ? err : -EIO;
			goto exit;
		}
	}

	{
		struct xnvme_cmd_ctx ctx = xnvme_cmd_ctx_from_dev(dev);
		uint64_t t0 = nsec_now();

		err = xnvme_znd_mgmt_send(&ctx, nsid, zslba, false,
					  XNVME_SPEC_ZND_CMD_MGMT_SEND_RESET, 0x0, NULL);
		reset_after_ns = nsec_now() - t0;
		if (err || xnvme_cmd_ctx_cpl_status(&ctx)) {
			fprintf(stderr, "zone reset after append failed: err=%d status=%d\n", err,
				xnvme_cmd_ctx_cpl_status(&ctx));
			err = err ? err : -EIO;
			goto exit;
		}
	}

	qsort(append_lat, append_count, sizeof(*append_lat), cmp_u64);
	printf("{\n");
	printf("  \"backend\": \"xnvme-linux-nvme-sync\",\n");
	printf("  \"device\": \"%s\",\n", uri);
	printf("  \"zone_index\": %" PRIu64 ",\n", zone_index);
	printf("  \"zslba\": %" PRIu64 ",\n", zslba);
	printf("  \"append_count\": %u,\n", append_count);
	printf("  \"lba_nbytes\": %u,\n", geo->lba_nbytes);
	printf("  \"zone_nsect\": %" PRIu64 ",\n", geo->nsect);
	printf("  \"append_total_ns\": %" PRIu64 ",\n", total_append_ns);
	printf("  \"append_avg_ns\": %.3f,\n", (double)total_append_ns / (double)append_count);
	printf("  \"append_p50_ns\": %" PRIu64 ",\n", percentile(append_lat, append_count, 50.0));
	printf("  \"append_p95_ns\": %" PRIu64 ",\n", percentile(append_lat, append_count, 95.0));
	printf("  \"append_p99_ns\": %" PRIu64 ",\n", percentile(append_lat, append_count, 99.0));
	printf("  \"append_min_ns\": %" PRIu64 ",\n", append_lat[0]);
	printf("  \"append_max_ns\": %" PRIu64 ",\n", append_lat[append_count - 1]);
	printf("  \"reset_before_ns\": %" PRIu64 ",\n", reset_before_ns);
	printf("  \"reset_after_ns\": %" PRIu64 ",\n", reset_after_ns);
	printf("  \"throughput_mib_s\": %.3f,\n",
	       ((double)append_count * (double)geo->lba_nbytes / (1024.0 * 1024.0)) /
		       ((double)total_append_ns / 1000000000.0));
	printf("  \"completed\": true\n");
	printf("}\n");

exit:
	if (buf) {
		xnvme_buf_free(dev, buf);
	}
	free(append_lat);
	if (dev) {
		xnvme_dev_close(dev);
	}
	return err ? 1 : 0;
}
