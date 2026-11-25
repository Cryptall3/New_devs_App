Property Revenue Dashboard: Bug Fixes

Name: Allwell
Video walkthrough: https://www.loom.com/share/b857cd4ad3804c81999d28b5c01d5d0e
Forked repository: https://github.com/Cryptall3/New_devs_App

WHAT WAS REPORTED

Sunset Properties said March revenue did not match their records. Ocean Rentals said they sometimes saw revenue that looked like another company's. Finance said some totals were off by a few cents.

WHAT I FOUND AND FIXED

1. Cross-tenant cache leak (Ocean's privacy complaint)

The revenue cache key was built from the property ID alone, for example revenue:prop-001. Both clients own a property with ID prop-001, so whichever client loaded first wrote its total into Redis and the other client read that same number for five minutes.

Fix: the cache key now includes the tenant, so each client's revenue is cached separately.

2. Wrong month for a Paris booking (Sunset's complaint)

One booking, res-tz-1, checks in at 2024-02-29 23:30 UTC. Beach House Alpha is in Europe/Paris, where that is 2024-03-01 00:30. The code grouped bookings by UTC month, so a March booking was counted in February.

Fix: the query now reads the property's timezone and calculates the month boundaries in local time. Grouped by UTC that month came to USD 1,000. Grouped in Paris local time it is USD 2,250, which is the USD 1,250 gap Sunset reported.

3. Cents drift

Amounts are stored as NUMERIC(10,3). The original code summed them through floating point and rounded more than once, so the error compounds. Fix: the sum stays a Decimal and is rounded once, half up, at the end.

For example, 2.675 rounds to 2.67 through float and 2.68 through Decimal.

To be accurate: the current seed data totals land exactly, so this was not producing a visibly wrong figure yet. It was one rounding away from doing so, and it is the same class of error finance noticed.

4. The database layer was failing silently

The database pool was built from settings that do not exist in this codebase, so every connection attempt failed. The revenue function caught that error and returned a hardcoded table of numbers instead. Those numbers ignored the tenant, which also contributed to the privacy issue.

Fix: the pool now uses the configured DATABASE_URL with the asyncpg driver, and the fallback is deleted. Failures now surface instead of returning invented figures. I also added the SQLAlchemy asyncio extra to requirements.txt, because a clean build otherwise crashes on a missing dependency.

5. Frontend tenant handling

The dashboard sent a hardcoded X-Simulated-Tenant header left over from debugging. The backend ignored it, but I removed it. The property dropdown was also hardcoded with all five properties, so Sunset could select Ocean's cottages. It is now filtered by the signed-in client's tenant.

I also made the API return 404 when a client requests a property they do not own, rather than a misleading 0.00. A 404 avoids confirming that the property ID exists for another tenant.

HOW I VERIFIED IT

Logged in as both clients and checked every property.

Sunset Properties:
prop-001 Beach House Alpha: USD 2,250.00, 4 bookings
prop-002 City Apartment Downtown: USD 4,975.50, 4 bookings
prop-003 Country Villa Estate: USD 6,100.50, 2 bookings

Ocean Rentals:
prop-001 Mountain Lodge Beta: USD 0.00, no bookings
prop-004 Lakeside Cottage: USD 1,776.50, 4 bookings
prop-005 Urban Loft Modern: USD 3,256.00, 3 bookings

The same property ID, prop-001, now returns different figures for each client, which confirms the cache and query isolation. Sunset no longer sees Ocean's properties in the dashboard.

SCOPE

This is a debugging exercise, so I kept changes small and stayed inside the existing structure. Nine files changed: four backend files, three frontend files, requirements.txt and .gitignore. Nothing was rebuilt.
