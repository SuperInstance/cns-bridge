"""
Tests for the NMEA → SWMIDI bridge.

Tests cover:
1. NMEA sentence parsing (GGA, RMC, DBT, HDT)
2. SWMIDI event encoding (correct pitch, velocity, error_mask)
3. 8-byte packing round-trip
4. Checksum validation
5. Error handling
6. Stream parsing
7. CC pair encoding for position/depth/heading
"""

import struct
import pytest

from cns_bridge.nmea_swmidi_bridge import (
    NmeaToSwmidi,
    SwmidiEvent,
    parse_gga,
    parse_rmc,
    parse_dbt,
    parse_hdt,
    _parse_lat_lon,
    _parse_nmea_checksum,
    PITCH_GPS_POSITION,
    PITCH_GPS_SOG,
    PITCH_GPS_COG,
    PITCH_DEPTH,
    PITCH_HEADING_TRUE,
    PITCH_FIX_QUALITY,
    PITCH_SATELLITE_COUNT,
    MASK_SEMANTIC,
    MASK_SAFETY,
    MASK_TOPOLOGY,
    MASK_RESOURCE,
)


# ── NMEA Parsing Tests ───────────────────────────────────────────────

class TestNmeaParsing:
    def test_gga_parse(self):
        """Parse a standard GGA sentence."""
        fields = "092204.999,5321.6802,N,00630.3371,W,1,04,2.0,100.5,M,,,,0000".split(",")
        data = parse_gga(fields)
        assert data['fix_quality'] == 1
        assert data['satellites'] == 4
        assert data['lat'] == pytest.approx(53.361337, abs=0.001)
        assert data['lon'] == pytest.approx(-6.505618, abs=0.001)
        assert data['altitude'] == 100.5

    def test_gga_no_fix(self):
        """GGA with no fix should have fix_quality=0."""
        fields = "092204.999,,,,,0,00,,,,M,,,,".split(",")
        data = parse_gga(fields)
        assert data['fix_quality'] == 0
        assert data['satellites'] == 0
        assert data['lat'] is None
        assert data['lon'] is None

    def test_rmc_parse(self):
        """Parse a standard RMC sentence."""
        fields = "083559.00,A,4717.11537,N,00833.91290,E,0.759,57.0,250623,,,A".split(",")
        data = parse_rmc(fields)
        assert data['status'] == 'A'  # active
        assert data['sog'] == pytest.approx(0.759)
        assert data['cog'] == pytest.approx(57.0)
        assert data['lat'] is not None
        assert data['lon'] is not None

    def test_rmc_warning(self):
        """RMC with status V should indicate invalid data."""
        fields = "083559.00,V,,,,,0.0,0.0,250623,,,".split(",")
        data = parse_rmc(fields)
        assert data['status'] == 'V'

    def test_dbt_parse(self):
        """Parse a depth below transducer sentence."""
        # DBT format: depth_feet, unit, depth_meters, unit, depth_fathoms, unit
        fields = "45.7,f,13.9,M,7.6,F".split(",")
        data = parse_dbt(fields)
        assert data['depth_feet'] == pytest.approx(45.7)
        assert data['depth_meters'] == pytest.approx(13.9)

    def test_dbt_empty(self):
        """DBT with no data should return None depths."""
        fields = ",f,,M,,F".split(",")
        data = parse_dbt(fields)
        assert data['depth_meters'] is None
        assert data['depth_feet'] is None

    def test_hdt_parse(self):
        """Parse heading true sentence."""
        fields = "234.5,T".split(",")
        data = parse_hdt(fields)
        assert data['heading_true'] == pytest.approx(234.5)

    def test_lat_lon_north(self):
        """Latitude parsing: N = positive."""
        assert _parse_lat_lon("5321.6802", "N") == pytest.approx(53.361337, abs=0.001)

    def test_lat_lon_south(self):
        """Latitude parsing: S = negative."""
        assert _parse_lat_lon("5321.6802", "S") == pytest.approx(-53.361337, abs=0.001)

    def test_lat_lon_east(self):
        """Longitude parsing: E = positive."""
        assert _parse_lat_lon("00630.3371", "E") == pytest.approx(6.505618, abs=0.001)

    def test_lat_lon_west(self):
        """Longitude parsing: W = negative."""
        assert _parse_lat_lon("00630.3371", "W") == pytest.approx(-6.505618, abs=0.001)

    def test_lat_lon_empty(self):
        """Empty value should return None."""
        assert _parse_lat_lon("", "N") is None


# ── Checksum Tests ───────────────────────────────────────────────────

class TestChecksum:
    def test_valid_checksum(self):
        """A sentence with correct checksum should pass."""
        # Known good sentence with correct checksum
        body, valid = _parse_nmea_checksum("$GPGGA,092204.999,5321.6802,N,00630.3371,W,1,04*76")
        assert valid is True

    def test_no_checksum(self):
        """A sentence without checksum should be accepted."""
        body, valid = _parse_nmea_checksum("$SDDBT,45.7,f,13.9,M,7.6,F")
        assert valid is True

    def test_invalid_checksum(self):
        """A sentence with bad checksum should fail."""
        body, valid = _parse_nmea_checksum("$GPGGA,data*XX")
        assert valid is False


# ── SWMIDI Event Tests ───────────────────────────────────────────────

class TestSwmidiEvent:
    def test_pack_8_bytes(self):
        """Event must pack to exactly 8 bytes."""
        event = SwmidiEvent(
            status=0x95, pitch=20, velocity=100, error_mask=0, tick=480
        )
        packed = event.pack()
        assert len(packed) == 8

    def test_unpack_roundtrip(self):
        """Pack → unpack should preserve all fields."""
        original = SwmidiEvent(
            status=0x95, pitch=20, velocity=100, error_mask=0x02, tick=99999
        )
        packed = original.pack()
        unpacked = SwmidiEvent.unpack(packed)
        assert unpacked.status == original.status
        assert unpacked.pitch == original.pitch
        assert unpacked.velocity == original.velocity
        assert unpacked.error_mask == original.error_mask
        assert unpacked.tick == original.tick

    def test_velocity_range(self):
        """Velocity must be 0-127."""
        for v in [0, 32, 64, 96, 127]:
            event = SwmidiEvent(status=0x90, pitch=0, velocity=v, error_mask=0, tick=0)
            assert 0 <= event.velocity <= 127

    def test_pitch_range(self):
        """Pitch must be 0-127."""
        for p in [0, 10, 20, 30, 127]:
            event = SwmidiEvent(status=0x90, pitch=p, velocity=64, error_mask=0, tick=0)
            assert event.pitch == p


# ── Bridge Tests ─────────────────────────────────────────────────────

class TestNmeaToSwmidi:
    def test_parse_dbt(self):
        """Depth sentence should produce a depth event."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$SDDBT,45.7,f,13.9,M,7.6,F*0A")
        assert len(events) == 1
        assert events[0].pitch == PITCH_DEPTH
        assert events[0].error_mask == 0  # 13.9m is fine

    def test_parse_shallow_depth_sets_safety(self):
        """Very shallow depth should set SAFETY bit."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$SDDBT,5.0,f,1.5,M,1.0,F*06")
        assert len(events) == 1
        assert events[0].error_mask & MASK_SAFETY

    def test_parse_hdt(self):
        """Heading sentence should produce a heading event."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$HCHDT,234.5,T*29")
        assert len(events) == 1
        assert events[0].pitch == PITCH_HEADING_TRUE
        assert events[0].velocity == 127  # heading always reliable

    def test_parse_gga(self):
        """GGA should produce position, fix quality, and satellite events."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$GPGGA,092204.999,5321.6802,N,00630.3371,W,1,04*76")
        assert len(events) == 3
        pitches = [e.pitch for e in events]
        assert PITCH_GPS_POSITION in pitches
        assert PITCH_FIX_QUALITY in pitches
        assert PITCH_SATELLITE_COUNT in pitches

    def test_parse_gga_no_fix(self):
        """GGA with no fix should set error mask."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$GPGGA,090000,,,,,0,00*43")
        assert len(events) >= 1
        # Position event should have topology error
        pos_events = [e for e in events if e.pitch == PITCH_GPS_POSITION]
        assert any(e.error_mask & MASK_TOPOLOGY for e in pos_events)

    def test_parse_rmc(self):
        """RMC should produce speed and course events."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$GPRMC,083559.00,A,4717.11537,N,00833.91290,E,0.759,57.0,250623,,,A")
        assert len(events) == 2
        pitches = [e.pitch for e in events]
        assert PITCH_GPS_SOG in pitches
        assert PITCH_GPS_COG in pitches

    def test_parse_rmc_warning(self):
        """RMC with status V should set SEMANTIC error."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$GPRMC,083559.00,V,,,,,0.0,0.0,250623,,,")
        assert len(events) >= 1
        assert all(e.error_mask & MASK_SEMANTIC for e in events)

    def test_parse_invalid_sentence(self):
        """Invalid sentence should return empty list."""
        bridge = NmeaToSwmidi()
        assert bridge.parse("") == []
        assert bridge.parse("not nmea") == []
        assert bridge.parse("$UNKNOWN,foo,bar") == []

    def test_tick_progression(self):
        """Each event should advance the BeatClock tick."""
        bridge = NmeaToSwmidi(channel=5, start_tick=0)
        events = bridge.parse("$HCHDT,180.0,T*20")
        assert len(events) == 1
        assert events[0].tick == 0

        events2 = bridge.parse("$HCHDT,190.0,T*21")
        assert len(events2) == 1
        assert events2[0].tick > 0  # advanced

    def test_channel_assignment(self):
        """Events should carry the assigned channel in status byte."""
        bridge = NmeaToSwmidi(channel=5)
        events = bridge.parse("$HCHDT,180.0,T*20")
        assert events[0].status & 0x0F == 5

    def test_stream_parsing(self):
        """Multiple sentences should parse in sequence."""
        bridge = NmeaToSwmidi()
        sentences = [
            "$SDDBT,45.7,f,13.9,M,7.6,F*0A",
            "$HCHDT,234.5,T*29",
            "$GPRMC,083559.00,A,4717.11,N,00833.91,E,0.759,57.0,250623,,,A",
        ]
        events = bridge.parse_stream(sentences)
        assert len(events) >= 3  # at least 1 per sentence
        # Ticks should be monotonically increasing
        ticks = [e.tick for e in events]
        for i in range(1, len(ticks)):
            assert ticks[i] > ticks[i - 1]

    def test_cc_pairs_for_position(self):
        """GPS position events should carry lat/lon in CC pairs."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$GPGGA,092204.999,5321.6802,N,00630.3371,W,1,04*76")
        pos_event = [e for e in events if e.pitch == PITCH_GPS_POSITION][0]
        assert len(pos_event.cc_pairs) >= 4  # lat high/low, lon high/low

    def test_cc_pairs_for_depth(self):
        """Depth events should carry depth in CC pairs."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$SDDBT,45.7,f,13.9,M,7.6,F*0A")
        assert len(events[0].cc_pairs) == 3  # 3 bytes for depth in cm

    def test_pack_events(self):
        """pack_events should produce correct binary format."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$HCHDT,234.5,T*29")
        packed = bridge.pack_events(events)
        assert len(packed) == 4 + 8 * len(events)  # count header + events

    def test_bad_checksum_returns_error_event(self):
        """A bad checksum should produce an error event."""
        bridge = NmeaToSwmidi()
        events = bridge.parse("$SDDBT,45.7,f,13.9,M,7.6,F*00")
        # Bad checksum → consistency error event
        assert len(events) == 1
        assert events[0].error_mask & (MASK_SEMANTIC | 0x80)  # SEMANTIC or CONSISTENCY


# ── Integration Tests ────────────────────────────────────────────────

class TestIntegration:
    def test_full_marine_session(self):
        """Simulate a real stream of marine data."""
        bridge = NmeaToSwmidi(channel=5, start_tick=0)

        # Simulate 30 seconds of marine data at 1Hz
        sentences = [
            "$GPGGA,092204.999,5321.6802,N,00630.3371,W,1,08,2.0,100.5,M,,,,*1D",
            "$GPRMC,092205.00,A,5321.6802,N,00630.3371,W,5.2,180.0,150826,,,A*4C",
            "$SDDBT,45.7,f,13.9,M,7.6,F*0A",
            "$HCHDT,182.3,T*21",
            "$SDDBT,44.9,f,13.7,M,7.5,F*7B",
            "$HCHDT,183.1,T*22",
        ]

        events = bridge.parse_stream(sentences)
        assert len(events) >= 6  # at least 1 per sentence

        # Verify all events have valid MIDI ranges
        for e in events:
            assert 0 <= e.pitch <= 127
            assert 0 <= e.velocity <= 127
            assert 0 <= e.error_mask <= 255
            assert e.tick >= 0

        # Verify the binary round-trips
        packed = bridge.pack_events(events)
        assert len(packed) == 4 + len(events) * 8
